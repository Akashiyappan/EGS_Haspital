from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.models import Specialization
from app.schemas.doctor import SpecializationCreate, SpecializationUpdate


async def list_specializations(db: AsyncSession, *, active_only: bool) -> list[Specialization]:
    query = select(Specialization).order_by(Specialization.name)
    if active_only:
        query = query.where(Specialization.is_active.is_(True))
    return list(await db.scalars(query))


async def get(db: AsyncSession, specialization_id: int) -> Specialization:
    specialization = await db.get(Specialization, specialization_id)
    if specialization is None:
        raise NotFoundError("Specialization not found")
    return specialization


async def _ensure_name_free(db: AsyncSession, name: str, exclude_id: int | None = None) -> None:
    query = select(Specialization.id).where(func.lower(Specialization.name) == name.lower())
    if exclude_id is not None:
        query = query.where(Specialization.id != exclude_id)
    if await db.scalar(query):
        raise ConflictError("A specialization with this name already exists", code="name_taken")


async def create(db: AsyncSession, data: SpecializationCreate) -> Specialization:
    await _ensure_name_free(db, data.name)
    specialization = Specialization(name=data.name, description=data.description)
    db.add(specialization)
    await db.flush()
    return specialization


async def update(
    db: AsyncSession, specialization: Specialization, data: SpecializationUpdate
) -> Specialization:
    changes = data.model_dump(exclude_unset=True)
    if changes.get("name"):
        await _ensure_name_free(db, changes["name"], exclude_id=specialization.id)
        specialization.name = changes["name"]
    if "description" in changes:
        specialization.description = changes["description"]
    if changes.get("is_active") is not None:
        specialization.is_active = changes["is_active"]
    await db.flush()
    return specialization


async def get_active_by_ids(db: AsyncSession, ids: list[int]) -> list[Specialization]:
    found = list(
        await db.scalars(
            select(Specialization).where(
                Specialization.id.in_(ids), Specialization.is_active.is_(True)
            )
        )
    )
    if len(found) != len(set(ids)):
        raise AppError("One or more specializations are invalid", code="invalid_specialization")
    return found
