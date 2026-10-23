from fastapi import APIRouter

from app.api.v1.routes import (
    admin,
    ai,
    appointments,
    auth,
    chat,
    doctor_portal,
    doctors,
    health,
    meta,
    notifications,
    prescriptions,
    records,
    users,
    ws,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(meta.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(doctors.router)
api_router.include_router(appointments.router)
api_router.include_router(prescriptions.router)
api_router.include_router(records.router)
api_router.include_router(chat.router)
api_router.include_router(notifications.router)
api_router.include_router(ai.router)
api_router.include_router(doctor_portal.router)
api_router.include_router(admin.router)
api_router.include_router(ws.router)
