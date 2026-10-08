from httpx import AsyncClient

from tests.helpers import API


async def test_liveness(client: AsyncClient) -> None:
    res = await client.get(f"{API}/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
    assert res.headers["X-Request-ID"]
    assert res.headers["X-Content-Type-Options"] == "nosniff"


async def test_readiness(client: AsyncClient) -> None:
    res = await client.get(f"{API}/health/ready")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "database": "up"}


async def test_request_id_is_propagated(client: AsyncClient) -> None:
    res = await client.get(f"{API}/health", headers={"X-Request-ID": "abc-123"})
    assert res.headers["X-Request-ID"] == "abc-123"


async def test_unknown_route_uses_error_envelope(client: AsyncClient) -> None:
    res = await client.get(f"{API}/does-not-exist")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "http_error"
