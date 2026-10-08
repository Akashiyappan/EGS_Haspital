"""MySQL-specific behaviour that can be verified without a MySQL server."""

from datetime import UTC, datetime, timedelta, timezone

import pymysql
import pytest
from httpx import AsyncClient
from sqlalchemy.dialects import mysql, sqlite
from sqlalchemy.exc import OperationalError
from sqlalchemy.schema import CreateIndex, CreateTable

from app.db.base import Base, UTCDateTime
from app.models import Appointment
from tests.helpers import API, iso, login, make_doctor, make_patient, slot_start


def test_datetimes_are_stored_as_naive_utc_with_microseconds_on_mysql() -> None:
    column = UTCDateTime()
    ist = timezone(timedelta(hours=5, minutes=30))
    bound = column.process_bind_param(
        datetime(2030, 1, 7, 8, 0, 0, 123456, tzinfo=ist), mysql.dialect()
    )
    assert bound == datetime(2030, 1, 7, 2, 30, 0, 123456)  # converted to UTC, tz stripped
    assert (
        str(column.load_dialect_impl(mysql.dialect()).compile(dialect=mysql.dialect()))
        == "DATETIME(6)"
    )
    read = column.process_result_value(datetime(2030, 1, 7, 2, 30), mysql.dialect())
    assert read == datetime(2030, 1, 7, 2, 30, tzinfo=UTC)


def test_naive_datetimes_are_rejected() -> None:
    with pytest.raises(ValueError):
        UTCDateTime().process_bind_param(datetime(2030, 1, 7, 8, 0), sqlite.dialect())


def test_double_booking_constraint_ddl_for_mysql() -> None:
    table = Appointment.__table__
    ddl = str(CreateTable(table).compile(dialect=mysql.dialect()))
    assert (
        "active_slot_starts_at DATETIME(6) GENERATED ALWAYS AS "
        "(CASE WHEN status IN ('BOOKED', 'CONFIRMED') THEN starts_at ELSE NULL END) STORED"
    ) in ddl
    indexes = {
        str(CreateIndex(index).compile(dialect=mysql.dialect()))
        for index in table.indexes
        if index.unique
    }
    assert indexes == {
        "CREATE UNIQUE INDEX uq_appointments_doctor_active_slot ON appointments (doctor_id, active_slot_starts_at)",
        "CREATE UNIQUE INDEX uq_appointments_patient_active_slot ON appointments (patient_id, active_slot_starts_at)",
    }


def test_identifiers_fit_mysql_limit() -> None:
    names = [
        str(item.name)
        for table in Base.metadata.sorted_tables
        for item in [*table.constraints, *table.indexes]
        if item.name
    ]
    assert names and all(len(name) <= 64 for name in names)


@pytest.mark.parametrize("errno", [1213, 1205])
async def test_innodb_lock_conflicts_become_409(
    client: AsyncClient, session_factory, monkeypatch: pytest.MonkeyPatch, errno: int
) -> None:
    """Racing inserts on MySQL can surface as a deadlock / lock-wait timeout
    rather than a duplicate key; the patient must still get a clean 409."""
    _, doctor = await make_doctor(session_factory)
    await make_patient(session_factory)
    headers = await login(client, "patient@example.com")

    from sqlalchemy.ext.asyncio import AsyncSession

    async def failing_flush(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise OperationalError("INSERT", {}, pymysql.err.OperationalError(errno, "lock conflict"))

    monkeypatch.setattr(AsyncSession, "flush", failing_flush)
    res = await client.post(
        f"{API}/appointments",
        json={"doctor_id": doctor.id, "starts_at": iso(slot_start())},
        headers=headers,
    )
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "slot_unavailable"
