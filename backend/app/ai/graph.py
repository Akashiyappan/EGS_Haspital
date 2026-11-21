"""LangGraph-driven decision graph for the hospital assistant.

Orchestrates automatic intent routing, deterministic safety guardrails,
conversational data gathering for appointment bookings, slot validation,
tool calling, and structured result generation.
"""

import contextlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.ai import safety
from app.ai.llm import LLMClient, LLMResponse, UnknownToolCallError
from app.ai.prompts.symptom_assistant import (
    DISCLAIMER,
    emergency_message,
)
from app.ai.schemas import (
    AppointmentConfirmation,
    AppointmentOption,
    AssistantResult,
)
from app.ai.tools import ToolContext, ToolRegistry, ToolTrace
from app.core.config import settings
from app.core.exceptions import AppError, ServiceUnavailableError
from app.core.pagination import PageParams
from app.core.timeutils import clinic_today
from app.models import (
    Doctor,
    Prescription,
    PrescriptionRequest,
    Specialization,
)
from app.services import (
    appointment_service,
    doctor_service,
    slot_service,
    specialization_service,
)

logger = logging.getLogger(__name__)

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)
_FINALIZE_INSTRUCTION = (
    "Stop using tools now. Reply with ONLY the final JSON object in the required format."
)

_APPOINTMENT_INTENT = re.compile(
    r"\b(book|booking|appointment|schedule|reserve|slot|slots|see a doctor|see dr\.?)\b", re.I
)
_DOCTOR_LIST_INTENT = re.compile(
    r"\b(?:list|show|find|all|names?)\b.{0,40}\b(?:doctors?|docters?)\b|"
    r"\b(?:doctors?|docters?)\b.{0,40}\b(?:list|names?|available|availability|slots?|times?)\b",
    re.I,
)
_DOCTOR_AVAILABILITY_INTENT = re.compile(
    r"\b(available|availability|slots?|times?|schedule|availability)\b", re.I
)
_MY_APPOINTMENTS_INTENT = re.compile(
    r"\b(?:my|view|show|list|check)\b.{0,40}\b(?:appointments?|visits?)\b|"
    r"\b(?:upcoming|past|previous)\s+(?:appointments?|visits?)\b",
    re.I,
)
_CANCEL_APPOINTMENT_INTENT = re.compile(
    r"\b(?:cancel|delete|remove)\b.{0,50}\b(?:my|upcoming|upcomming|appointment|appoint\w*)\b",
    re.I,
)
_PORTAL_HELP_INTENT = re.compile(
    r"\b(what (?:can|does) (?:i|this portal|this app)|portal features|app features|"
    r"what features (?:are )?(?:available|here)|how (?:do|can) i use (?:the )?(?:portal|app)|"
    r"how (?:do|can) i (?:request|get|view) (?:a )?prescriptions?|what can i do here)\b",
    re.I,
)
_PRESCRIPTION_INTENT = re.compile(
    r"\b(my prescriptions?|my medicines?|my medications?|prescription dosage|"
    r"what medicines? (?:am i|do i) (?:currently )?(?:take|prescribed)|"
    r"what (?:was|did) (?:the doctor|my doctor) prescribe|prescription request|"
    r"request status|medication list|(?:what )?(?:prescriptions?|medications?)"
    r"(?: are)?(?: currently)? (?:in|on) my (?:account|records?))\b",
    re.I,
)
_AUTHORIZE_BOOKING = re.compile(r"\b(book|schedule|reserve|confirm|take that|lock in)\b", re.I)
_DO_NOT_BOOK = re.compile(
    r"\b(don't|do not|not|never|cancel)\b.{0,30}\b(book|schedule|reserve|confirm)\b", re.I
)
_TIME_PATTERN = re.compile(
    r"\b(?:at\s*)?(?:(\d{1,2}):(\d{2})\s*(am|pm)?|(\d{1,2})\s*(am|pm))\b", re.I
)
_SPECIFIC_SLOT_SELECTION = re.compile(
    r"\b(it|that slot|that time|this slot|this time|first slot)\b", re.I
)


def parse_result(content: str | None) -> AssistantResult | None:
    if not content:
        return None
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    match = _JSON_OBJECT_RE.search(text)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
        if not isinstance(data, dict):
            return None
        return AssistantResult.model_validate(_coerce(data))
    except (json.JSONDecodeError, ValidationError):
        return None


def _coerce(data: dict[str, Any]) -> dict[str, Any]:
    limits = {
        "possible_concerns": 5,
        "recommended_specializations": 5,
        "recommended_doctor_ids": 5,
        "next_steps": 5,
        "follow_up_questions": 3,
    }
    for key, limit in limits.items():
        value = data.get(key)
        if isinstance(value, list):
            data[key] = [str(v)[:300] for v in value if str(v).strip()][:limit]
    ids = []
    for value in data.get("recommended_doctor_ids") or []:
        try:
            ids.append(int(value))
        except (TypeError, ValueError):
            continue
    data["recommended_doctor_ids"] = ids
    if data.get("urgency") not in ("emergency", "urgent", "routine", "self_care"):
        data["urgency"] = "routine"
    data.pop("emergency_message", None)
    data.pop("disclaimer", None)
    return data


@dataclass
class AgentRun:
    result: AssistantResult | None
    termination: str
    tool_traces: list[ToolTrace] = field(default_factory=list)
    iterations: int = 0
    tokens: int = 0
    latency_ms: int = 0


class HospitalGraphState(TypedDict, total=False):
    messages: list[dict[str, Any]]
    context: ToolContext
    llm: LLMClient | None
    registry: ToolRegistry
    route: str
    result: AssistantResult | None
    tool_traces: list[ToolTrace]
    iterations: int
    tokens: int
    termination: str
    unknown_tool_retries: int
    latest_response: LLMResponse | None


# --- Intent classification and entity extraction ---------------------------------


_SLOT_SELECTION_PHRASES = re.compile(
    r"\b(that slot|that time|this slot|this time|first slot|the earlier slot)\b|"
    r"\b(?:book|schedule|reserve|confirm|take)\s+it\b",
    re.I,
)
_UPCOMING_AVAILABILITY_INTENT = re.compile(
    r"\b(future|upcoming|next few days|next week|availability|"
    r"doctor(?:'s)? schedule|schedule of (?:the )?doctor|open appointment times?)\b",
    re.I,
)
_BOOKING_ACKNOWLEDGEMENT = re.compile(
    r"^\s*(?:okay?(?:\s+proceed)?|yes|sure|proceed|continue|go ahead|do it)"
    r"(?:\s+please)?[.!\s]*$",
    re.I,
)
_GENERIC_SLOT_BOOKING = re.compile(r"\b(?:book|reserve|schedule)\s+(?:the|a)\s+slot\b", re.I)


def classify_intent(text: str, history: list[dict[str, Any]], has_llm: bool, ctx: ToolContext | None = None) -> str:
    if safety.is_prompt_injection(text):
        return "refusal"

    has_red = safety.has_red_flags(text)

    # Check if conversation history is in an active booking dialogue:
    in_booking_dialogue = False
    last_assistant_text = ""
    if len(history) >= 2:
        last_assistant = history[-2]
        if last_assistant.get("role") == "assistant":
            last_content = (last_assistant.get("content") or "").lower()
            last_assistant_text = last_content
            if any(
                phrase in last_content
                for phrase in (
                    "which date",
                    "which time",
                    "choose a slot",
                    "choose a date",
                    "choose a doctor",
                    "choose a specialization",
                    "specializations include",
                    "open slots",
                    "open appointment slots",
                    "available appointment times",
                    "choose another specialty",
                    "recommended_doctor_ids",
                )
            ):
                in_booking_dialogue = True

    is_date_reply = bool(
        re.search(r"\b(today|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", text, re.I)
        or re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", text)
    )

    # Slot selection in active appointment context:
    has_active_slots = bool(ctx and ctx.appointment_options)
    is_slot_pick = bool(
        _SLOT_SELECTION_PHRASES.search(text)
        or (has_active_slots and re.search(r"\b(it|that|this|first)\b", text, re.I))
        or _TIME_PATTERN.search(text)
    )
    is_booking_request = bool(
        _APPOINTMENT_INTENT.search(text)
        or is_slot_pick
        or (in_booking_dialogue and (is_date_reply or is_slot_pick or _TIME_PATTERN.search(text)))
        or (
            in_booking_dialogue
            and _BOOKING_ACKNOWLEDGEMENT.fullmatch(text)
            and ("slot" in last_assistant_text or "appointment time" in last_assistant_text)
        )
        or (
            in_booking_dialogue
            and len(text.strip()) <= 80
            and text.lower().strip() in last_assistant_text
            and not _APPOINTMENT_INTENT.search(text)
            and not _BOOKING_ACKNOWLEDGEMENT.fullmatch(text)
        )
    )

    # When no LLM is configured:
    if not has_llm:
        if has_red:
            return "emergency"
        if _PORTAL_HELP_INTENT.search(text):
            return "portal_help"
        if _PRESCRIPTION_INTENT.search(text):
            return "prescription"
        if _CANCEL_APPOINTMENT_INTENT.search(text) or _MY_APPOINTMENTS_INTENT.search(text):
            return "my_appointments"
        if _DOCTOR_LIST_INTENT.search(text) and not _UPCOMING_AVAILABILITY_INTENT.search(text):
            return "doctor_directory"
        if is_booking_request:
            return "booking"
        return "unconfigured"

    # When LLM is configured:
    # If red flags appear alongside explicit booking authorization, emergency safety applies.
    if has_red and (_AUTHORIZE_BOOKING.search(text) and not _DO_NOT_BOOK.search(text)):
        return "emergency"

    # Deterministic hospital portal features:
    if not has_red:
        if _PORTAL_HELP_INTENT.search(text):
            return "portal_help"
        if _PRESCRIPTION_INTENT.search(text):
            return "prescription"
        if _CANCEL_APPOINTMENT_INTENT.search(text) or _MY_APPOINTMENTS_INTENT.search(text):
            return "my_appointments"
        if _DOCTOR_LIST_INTENT.search(text) and not _UPCOMING_AVAILABILITY_INTENT.search(text):
            return "doctor_directory"
        # Booking intent or slot selection:
        if is_booking_request:
            return "booking"

    return "llm_call"


async def extract_booking_entities(
    text: str, messages: list[dict[str, Any]], ctx: ToolContext
) -> dict[str, Any]:
    """Extract doctor, date, time slot, and booking authorization from text and context."""
    db = ctx.db
    now = ctx.now
    today = clinic_today(now)

    extracted_doctor: Doctor | None = None
    extracted_specialization: Specialization | None = None
    extracted_date: date | None = None
    extracted_time: str | None = None
    is_relative_slot = False
    is_authorized = bool(_AUTHORIZE_BOOKING.search(text) and not _DO_NOT_BOOK.search(text))

    # 1. Doctor ID extraction: e.g. "doctor 2", "dr 2", "doctor #2", "id 2"
    doc_id_match = re.search(r"\b(?:doctor|dr\.?)\s*(?:id\s*)?#?(\d+)\b", text, re.I) or re.search(
        r"\bid\s*#?(\d+)\b", text, re.I
    )
    if doc_id_match:
        doc_id = int(doc_id_match.group(1))
        extracted_doctor = await db.get(Doctor, doc_id)
        if extracted_doctor and not (extracted_doctor.user and extracted_doctor.user.is_active):
            extracted_doctor = None

    # 2. Doctor Name extraction: e.g. "Dr. Gina", "Dr Gina", "Gina", "Dr. Carter"
    if extracted_doctor is None:
        doc_name_match = re.search(r"\bdr\.?\s+([A-Za-z]+)(?:\s+([A-Za-z]+))?\b", text, re.I)
        if doc_name_match:
            first_part = doc_name_match.group(1).strip()
            second_part = (doc_name_match.group(2) or "").strip()
            stop_words = {
                "today", "tomorrow", "at", "on", "in", "for", "please",
                "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
            }
            if second_part.lower() in stop_words:
                query_name = first_part
            elif second_part:
                query_name = f"{first_part} {second_part}"
            else:
                query_name = first_part

            matched_docs, _ = await doctor_service.list_doctors(
                db, PageParams(page=1, page_size=1), public=True, search=query_name
            )
            if not matched_docs and " " in query_name:
                matched_docs, _ = await doctor_service.list_doctors(
                    db, PageParams(page=1, page_size=1), public=True, search=first_part
                )
            if matched_docs:
                extracted_doctor = matched_docs[0]

    # 3. Specialization extraction:
    specializations = await specialization_service.list_specializations(db, active_only=True)
    text_lower = text.lower()
    for spec in specializations:
        if re.search(rf"\b{re.escape(spec.name.lower())}\b", text_lower) or (
            spec.name.lower() == "general medicine"
            and re.search(r"\b(gen(?:e|a)ral|gp|check[- ]?up|health check)\b", text_lower)
        ):
            extracted_specialization = spec
            break

    # Reuse a doctor only when the prior live offer identifies one unambiguous doctor.
    if extracted_doctor is None:
        if ctx.appointment_options:
            doc_id = ctx.appointment_options[0]["doctor_id"]
            extracted_doctor = await db.get(Doctor, doc_id)
        elif ctx.prior_appointment_options and extracted_specialization is None:
            prior_doctor_ids = {
                int(option["doctor_id"])
                for option in ctx.prior_appointment_options
                if option.get("doctor_id") is not None
            }
            if len(prior_doctor_ids) == 1:
                extracted_doctor = await db.get(Doctor, next(iter(prior_doctor_ids)))
        elif ctx.seen_doctor_ids:
            doc_id = next(iter(ctx.seen_doctor_ids))
            extracted_doctor = await db.get(Doctor, doc_id)
        elif messages and len(messages) > 1 and extracted_specialization is None:
            for m in reversed(messages[:-1]):
                content = m.get("content", "")
                rec_match = re.search(r"recommended_doctor_ids=\[([0-9,\s]+)\]", content)
                if rec_match:
                    first_id_str = rec_match.group(1).split(",")[0].strip()
                    if first_id_str.isdigit():
                        candidate = await db.get(Doctor, int(first_id_str))
                        if candidate:
                            extracted_doctor = candidate
                            break
                prev_doc_match = re.search(r"\bdr\.?\s+([A-Za-z]+)\b", content, re.I)
                if prev_doc_match:
                    matched_docs, _ = await doctor_service.list_doctors(
                        db, PageParams(page=1, page_size=1), public=True, search=prev_doc_match.group(1)
                    )
                    if matched_docs:
                        extracted_doctor = matched_docs[0]
                        break

    # 4. Date extraction:
    if re.search(r"\btoday\b", text, re.I) and not re.search(
        r"\b(?:not|no|except|instead of)\s+today\b", text, re.I
    ):
        extracted_date = today
    elif re.search(r"\btomorrow\b", text, re.I):
        extracted_date = today + timedelta(days=1)
    elif re.search(r"\bday after tomorrow\b", text, re.I):
        extracted_date = today + timedelta(days=2)
    else:
        # Check weekdays (monday, tuesday, ...)
        weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        for idx, wday in enumerate(weekdays):
            if re.search(rf"\b{wday}\b", text, re.I):
                days_ahead = (idx - today.weekday()) % 7
                if days_ahead == 0:
                    days_ahead = 7
                extracted_date = today + timedelta(days=days_ahead)
                break

    # Check ISO date format YYYY-MM-DD
    if extracted_date is None:
        iso_match = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", text)
        if iso_match:
            with contextlib.suppress(ValueError):
                extracted_date = date(int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3)))

    # Fallback to date from previously offered slots or messages if available
    if extracted_date is None and ctx.appointment_options:
        first_opt = ctx.appointment_options[0]
        with contextlib.suppress(Exception):
            extracted_date = (
                datetime.fromisoformat(first_opt["starts_at"]).astimezone(settings.clinic_tz).date()
            )
    # 5. Time extraction: e.g. "10:00", "10am", "2:30 pm"
    time_match = _TIME_PATTERN.search(text)
    if time_match:
        if time_match.group(1) is not None:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2))
            ampm = (time_match.group(3) or "").lower()
        else:
            hour = int(time_match.group(4))
            minute = 0
            ampm = (time_match.group(5) or "").lower()
        if ampm == "pm" and hour < 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
        extracted_time = f"{hour:02d}:{minute:02d}"

    # 6. Relative slot: "that slot", "it", "this time"
    if _SPECIFIC_SLOT_SELECTION.search(text):
        is_relative_slot = True
        if extracted_time is None and ctx.appointment_options:
            extracted_time = ctx.appointment_options[0].get("local_time")

    # Recover a date only from a persisted live slot offer, never from prose in
    # an old assistant reply that might contain a stale date.
    matching_prior_options = [
        option
        for option in ctx.prior_appointment_options
        if (extracted_doctor is None or option.get("doctor_id") == extracted_doctor.id)
        and (
            extracted_specialization is None
            or option.get("specialization", "").lower() == extracted_specialization.name.lower()
        )
    ]
    if extracted_time is not None:
        matching_prior_options = [
            option
            for option in matching_prior_options
            if str(option.get("local_time", "")).endswith(extracted_time)
        ]
    elif is_relative_slot and len(matching_prior_options) == 1:
        local_value = str(matching_prior_options[0].get("local_time", ""))
        time_value = local_value.rsplit(" ", 1)[-1]
        if re.fullmatch(r"\d{2}:\d{2}", time_value):
            extracted_time = time_value

    if extracted_date is None and len(matching_prior_options) == 1:
        with contextlib.suppress(Exception):
            extracted_date = datetime.fromisoformat(
                matching_prior_options[0]["starts_at"]
            ).astimezone(settings.clinic_tz).date()

    if extracted_time is not None:
        is_authorized = True

    return {
        "doctor": extracted_doctor,
        "specialization": extracted_specialization,
        "date": extracted_date,
        "time_str": extracted_time,
        "is_relative_slot": is_relative_slot,
        "is_authorized": is_authorized,
    }


# --- LangGraph Nodes -------------------------------------------------------------


async def router_node(state: HospitalGraphState) -> dict[str, Any]:
    ctx = state["context"]
    text = ctx.current_text
    messages = state["messages"]
    has_llm = state.get("llm") is not None
    route = classify_intent(text, messages, has_llm, ctx)
    logger.info("LangGraph router decision: %s for input_len=%d", route, len(text))
    return {"route": route}


async def refusal_node(state: HospitalGraphState) -> dict[str, Any]:
    return {"result": safety.refusal_result(), "termination": "refused"}


async def emergency_node(state: HospitalGraphState) -> dict[str, Any]:
    result = AssistantResult(
        summary=emergency_message(),
        urgency="emergency",
        emergency_message=emergency_message(),
        disclaimer=DISCLAIMER,
    )
    return {"result": result, "termination": "emergency"}


async def portal_help_node(state: HospitalGraphState) -> dict[str, Any]:
    summary = (
        "You can find doctors and view their profiles in Find a doctor; book and manage visits in Appointments; "
        "request a doctor's prescription review and view issued prescriptions in Prescriptions; review visit notes "
        "in Health records; contact your care team in Messages; and manage your account in Profile. You can also "
        "use this AI assistant for general symptom guidance and help finding care. A doctor must review and issue "
        "prescriptions, and this assistant cannot diagnose or prescribe."
    )
    result = AssistantResult(summary=summary, response_type="follow_up", urgency="routine", disclaimer=DISCLAIMER)
    return {"result": result, "termination": "retrieval"}


async def prescription_node(state: HospitalGraphState) -> dict[str, Any]:
    ctx = state["context"]
    db = ctx.db
    now = ctx.now

    if ctx.patient is None:
        result = AssistantResult(
            summary="Sign in to the patient portal to view your prescription records.",
            response_type="follow_up",
            urgency="routine",
            disclaimer=DISCLAIMER,
        )
        return {"result": result, "termination": "retrieval"}

    rows = await db.scalars(
        select(Prescription)
        .where(Prescription.patient_id == ctx.patient.id)
        .options(
            selectinload(Prescription.items),
            selectinload(Prescription.doctor).selectinload(Doctor.user),
        )
        .order_by(Prescription.created_at.desc(), Prescription.id.desc())
        .limit(5)
    )
    requests = await db.scalars(
        select(PrescriptionRequest)
        .where(PrescriptionRequest.patient_id == ctx.patient.id)
        .options(selectinload(PrescriptionRequest.doctor).selectinload(Doctor.user))
        .order_by(PrescriptionRequest.created_at.desc(), PrescriptionRequest.id.desc())
        .limit(5)
    )
    prescriptions = list(rows)
    prescription_requests = list(requests)
    ctx.prescription_lookup_completed = True

    sections: list[str] = []
    if prescriptions:
        rx_lines = []
        for rx in prescriptions:
            issued_date = rx.created_at.date().isoformat() if rx.created_at else "date unavailable"
            duration = max((item.duration_days for item in rx.items), default=0)
            course_end = (rx.created_at.date() + timedelta(days=duration)) if rx.created_at else clinic_today(now)
            course_status = "course period active" if clinic_today(now) <= course_end else "course period ended"
            medicines = "; ".join(
                f"{item.medicine_name}: {item.dosage}, {item.frequency}, {item.timing}, "
                f"for {item.duration_days} days"
                + (f"; instructions: {item.instructions}" if item.instructions else "")
                for item in rx.items
            )
            rx_lines.append(
                f"RX-{rx.id:06d}, issued {issued_date} by Dr. {rx.doctor.user.full_name}; "
                f"diagnosis recorded: {rx.diagnosis}; {course_status}. Medicines: {medicines or 'none listed'}."
            )
        sections.append("Your latest doctor-issued prescriptions: " + " ".join(rx_lines))
    else:
        sections.append("There are no doctor-issued prescriptions in your records yet.")

    if prescription_requests:
        request_lines = [
            f"Request #{request.id} to Dr. {request.doctor.user.full_name} is {request.status.lower()} "
            f"(submitted {request.created_at.date().isoformat()})."
            for request in prescription_requests
        ]
        sections.append("Prescription requests: " + " ".join(request_lines))
    else:
        sections.append("You have no prescription requests on record.")

    sections.append(
        "These details are copied from your records. Follow the prescribing doctor's instructions; "
        "contact the doctor or pharmacist before changing a medicine or dose. The assistant cannot issue or change prescriptions."
    )
    result = AssistantResult(
        summary=" ".join(sections),
        response_type="follow_up",
        urgency="routine",
        disclaimer=DISCLAIMER,
    )
    return {"result": result, "termination": "retrieval"}


async def doctor_directory_node(state: HospitalGraphState) -> dict[str, Any]:
    ctx = state["context"]
    text = ctx.current_text
    if _DOCTOR_AVAILABILITY_INTENT.search(text):
        booking_data = await extract_booking_entities(text, state["messages"], ctx)
        target_specialization: Specialization | None = booking_data["specialization"]
        target_date: date | None = booking_data["date"]
        doctors, _ = await doctor_service.list_doctors(
            ctx.db,
            PageParams(page=1, page_size=20),
            public=True,
            specialization_id=target_specialization.id if target_specialization else None,
        )
        ctx.doctor_directory_ids = [doctor.id for doctor in doctors]
        ctx.seen_doctor_ids.update(ctx.doctor_directory_ids)
        first_day = target_date or clinic_today(ctx.now)
        last_day = target_date or (first_day + timedelta(days=13))
        options: list[dict[str, Any]] = []
        tz = settings.clinic_tz
        for doctor in doctors:
            schedule = await slot_service.slots_for_range(
                ctx.db, doctor.id, first_day, last_day, ctx.now
            )
            specialization = next(
                (
                    item.name
                    for item in doctor.specializations
                    if target_specialization and item.id == target_specialization.id
                ),
                doctor.specializations[0].name if doctor.specializations else "General Medicine",
            )
            for slots in schedule.values():
                for slot in slots:
                    if not slot.available:
                        continue
                    options.append(
                        {
                            "doctor_id": doctor.id,
                            "doctor_name": f"Dr. {doctor.user.full_name}",
                            "specialization": specialization,
                            "starts_at": slot.starts_at.isoformat(),
                            "local_time": slot.starts_at.astimezone(tz).strftime("%d %b %Y, %H:%M"),
                        }
                    )
                    ctx.available_slots.add(
                        (doctor.id, slot.starts_at.astimezone(UTC).isoformat())
                    )
        options.sort(key=lambda option: option["starts_at"])
        ctx.appointment_options = options[:10]
        doctor_names = ", ".join(f"Dr. {doctor.user.full_name}" for doctor in doctors[:10])
        scope = (
            f"{target_specialization.name} doctors"
            if target_specialization
            else "doctors"
        )
        if ctx.appointment_options:
            available = "; ".join(
                f"{option['doctor_name']} ({option['specialization']}) — {option['local_time']}"
                for option in ctx.appointment_options
            )
            summary = f"Available {scope}: {available}. Choose a slot to book."
        elif doctors:
            date_text = (
                target_date.strftime("%A, %d %B %Y")
                if target_date
                else "the next 14 days"
            )
            summary = (
                f"Doctors available in {scope}: {doctor_names}. "
                f"I couldn't find an open slot for {date_text}."
            )
        else:
            summary = f"I couldn't find any active {scope} at this hospital."
        result = AssistantResult(
            summary=summary,
            response_type="appointment",
            urgency="routine",
            recommended_specializations=[target_specialization.name] if target_specialization else [],
            recommended_doctor_ids=list(
                dict.fromkeys(option["doctor_id"] for option in ctx.appointment_options)
            )[:5],
            appointment_options=[
                AppointmentOption.model_validate(option) for option in ctx.appointment_options
            ],
            disclaimer=DISCLAIMER,
        )
        return {"result": result, "termination": "doctor_directory_availability"}

    doctors, _ = await doctor_service.list_doctors(
        ctx.db, PageParams(page=1, page_size=20), public=True
    )
    ctx.doctor_directory_ids = [d.id for d in doctors]
    ctx.seen_doctor_ids.update(ctx.doctor_directory_ids)
    names = ", ".join(f"Dr. {doctor.user.full_name}" for doctor in doctors)
    summary = (
        f"Doctors currently listed at this hospital: {names}. "
        "Tell me a doctor's name or specialty to check available appointment times."
        if doctors
        else "There are no active doctors listed right now. Please contact the hospital for help."
    )
    result = AssistantResult(
        summary=summary,
        response_type="follow_up",
        urgency="routine",
        disclaimer=DISCLAIMER,
    )
    return {"result": result, "termination": "retrieval"}


async def my_appointments_node(state: HospitalGraphState) -> dict[str, Any]:
    ctx = state["context"]
    text = ctx.current_text.lower()
    scope = "past" if re.search(r"\b(past|previous|history|last)\b", text) else "upcoming"
    appointments, total = await appointment_service.list_for_user(
        ctx.db,
        ctx.patient_user,
        PageParams(page=1, page_size=5),
        scope=scope,
        now=ctx.now,
    )
    if appointments:
        lines = [
            f"Dr. {item.doctor.user.full_name} — "
            f"{item.starts_at.astimezone(settings.clinic_tz).strftime('%A, %d %b %Y at %H:%M')} "
            f"({item.status.value.lower().replace('_', ' ')})"
            for item in appointments
        ]
        summary = f"Your {scope} appointments: {'; '.join(lines)}."
        if total > len(appointments):
            summary += f" Showing {len(appointments)} of {total}."
        if scope == "upcoming" and _CANCEL_APPOINTMENT_INTENT.search(text):
            summary += (
                " To cancel one, open Appointments and choose Cancel beside the appointment "
                "you want to remove."
            )
    else:
        summary = f"You have no {scope} appointments in the portal right now."
    result = AssistantResult(
        summary=summary,
        response_type="follow_up",
        urgency="routine",
        disclaimer=DISCLAIMER,
    )
    return {"result": result, "termination": "patient_appointments"}


async def booking_node(state: HospitalGraphState) -> dict[str, Any]:
    """Automatic decision and data gathering engine for appointment bookings.

    Decides what data is missing, gathers details conversationally,
    validates slots with the clinic calendar, and books appointments.
    """
    ctx = state["context"]
    db = ctx.db
    now = ctx.now
    today = clinic_today(now)
    text = ctx.current_text

    booking_data = await extract_booking_entities(text, state["messages"], ctx)
    doctor: Doctor | None = booking_data["doctor"]
    target_date: date | None = booking_data["date"]
    time_str: str | None = booking_data["time_str"]
    is_authorized: bool = booking_data["is_authorized"]

    specializations = await specialization_service.list_specializations(db, active_only=True)
    spec_names = [s.name for s in specializations]

    # --- Step 1: Missing Doctor / Specialization ---
    if doctor is None:
        target_specialization: Specialization | None = booking_data["specialization"]
        if target_specialization is not None:
            doctors, _ = await doctor_service.list_doctors(
                db,
                PageParams(page=1, page_size=20),
                public=True,
                specialization_id=target_specialization.id,
            )
            ctx.doctor_directory_ids = [candidate.id for candidate in doctors]
            ctx.seen_doctor_ids.update(ctx.doctor_directory_ids)
            first_day = target_date or today
            last_day = target_date or (first_day + timedelta(days=13))
            tz = settings.clinic_tz
            options: list[dict[str, Any]] = []
            for candidate in doctors:
                candidate_spec = next(
                    (
                        item.name
                        for item in candidate.specializations
                        if item.id == target_specialization.id
                    ),
                    target_specialization.name,
                )
                schedule = await slot_service.slots_for_range(
                    db, candidate.id, first_day, last_day, now
                )
                for slots in schedule.values():
                    for slot in slots:
                        if not slot.available:
                            continue
                        options.append(
                            {
                                "doctor_id": candidate.id,
                                "doctor_name": f"Dr. {candidate.user.full_name}",
                                "specialization": candidate_spec,
                                "starts_at": slot.starts_at.isoformat(),
                                "local_time": slot.starts_at.astimezone(tz).strftime(
                                    "%d %b %Y, %H:%M"
                                ),
                            }
                        )
                        ctx.available_slots.add(
                            (candidate.id, slot.starts_at.astimezone(UTC).isoformat())
                        )
            options.sort(key=lambda option: option["starts_at"])
            ctx.appointment_options = options[:10]
            if ctx.appointment_options:
                times = "; ".join(
                    f"{option['doctor_name']} — {option['local_time']}"
                    for option in ctx.appointment_options
                )
                summary = (
                    f"Here are the available {target_specialization.name} doctors and appointment "
                    f"times: {times}. Choose a slot to book."
                )
            elif doctors:
                date_label = (
                    target_date.strftime("%A, %d %B %Y")
                    if target_date
                    else "the next 14 days"
                )
                summary = (
                    f"I found {len(doctors)} active {target_specialization.name} doctor(s), but "
                    f"there are no open slots for {date_label}. Would you like to check another date?"
                )
            else:
                summary = (
                    f"I couldn't find an active doctor in {target_specialization.name}. "
                    "Would you like to choose another specialty?"
                )
            result = AssistantResult(
                summary=summary,
                response_type="appointment",
                urgency="routine",
                recommended_specializations=[target_specialization.name],
                recommended_doctor_ids=list(dict.fromkeys(
                    option["doctor_id"] for option in ctx.appointment_options
                ))[:5],
                appointment_options=[
                    AppointmentOption.model_validate(option)
                    for option in ctx.appointment_options
                ],
                next_steps=["Choose one of the listed appointment times to book."],
                disclaimer=DISCLAIMER,
            )
            return {"result": result, "termination": "booking_specialty_availability"}

        summary = (
            f"I'd be glad to help you book an appointment! Which medical specialization "
            f"or doctor would you like to see? Available specializations include: {', '.join(spec_names[:5])}."
        )
        result = AssistantResult(
            summary=summary,
            response_type="appointment",
            urgency="routine",
            recommended_specializations=spec_names[:5],
            next_steps=["Choose a doctor or specialization to check open appointment slots."],
            disclaimer=DISCLAIMER,
        )
        return {"result": result, "termination": "booking_gathering_doctor"}

    ctx.seen_doctor_ids.add(doctor.id)
    doc_name = f"Dr. {doctor.user.full_name}"
    doc_spec = doctor.specializations[0].name if doctor.specializations else "General Medicine"

    # --- Step 2: Doctor known, Date missing ---
    if target_date is None:
        previous_assistant = (
            state["messages"][-2].get("content", "").lower()
            if len(state["messages"]) >= 2
            and state["messages"][-2].get("role") == "assistant"
            else ""
        )
        acknowledging_slot_offer = bool(
            _BOOKING_ACKNOWLEDGEMENT.fullmatch(text)
            and ("slot" in previous_assistant or "appointment time" in previous_assistant)
        )
        if (
            _UPCOMING_AVAILABILITY_INTENT.search(text)
            or acknowledging_slot_offer
            or _GENERIC_SLOT_BOOKING.search(text)
        ):
            days = await slot_service.slots_for_range(
                db, doctor.id, today, today + timedelta(days=13), now
            )
            tz = settings.clinic_tz
            upcoming_options = []
            for _, slots in days.items():
                for slot in slots:
                    if not slot.available:
                        continue
                    option = {
                        "doctor_id": doctor.id,
                        "doctor_name": doc_name,
                        "specialization": doc_spec,
                        "starts_at": slot.starts_at.isoformat(),
                        "local_time": slot.starts_at.astimezone(tz).strftime("%d %b %Y, %H:%M"),
                    }
                    upcoming_options.append(option)
                    ctx.available_slots.add((doctor.id, slot.starts_at.astimezone(UTC).isoformat()))
            upcoming_options.sort(key=lambda option: option["starts_at"])
            ctx.appointment_options = upcoming_options[:10]
            if upcoming_options:
                choices = "; ".join(option["local_time"] for option in ctx.appointment_options)
                summary = (
                    f"Upcoming available appointment times with {doc_name} ({doc_spec}) "
                    f"in clinic time: {choices}. Choose a date and time to continue."
                )
            else:
                summary = (
                    f"I couldn't find an open appointment time with {doc_name} ({doc_spec}) "
                    "in the next 14 days. Would you like to check another doctor or specialty?"
                )
            result = AssistantResult(
                summary=summary,
                response_type="appointment",
                urgency="routine",
                recommended_specializations=[doc_spec],
                recommended_doctor_ids=[doctor.id],
                appointment_options=[
                    AppointmentOption.model_validate(opt) for opt in ctx.appointment_options
                ],
                disclaimer=DISCLAIMER,
            )
            return {"result": result, "termination": "booking_upcoming_availability"}

        # Check upcoming 7 days availability
        days = await slot_service.slots_for_range(db, doctor.id, today, today + timedelta(days=7), now)
        open_days = [day for day, slots in days.items() if any(s.available for s in slots)]
        if open_days:
            formatted_days = [d.strftime("%A (%d %b)") for d in open_days[:4]]
            summary = (
                f"{doc_name} ({doc_spec}) has open appointment slots on: {', '.join(formatted_days)}. "
                f"Which date works best for you? (You can say 'tomorrow' or give a specific date)."
            )
        else:
            summary = (
                f"{doc_name} has no open appointment slots in the next 7 days. "
                f"Would you like to check a later date or look at another doctor in {doc_spec}?"
            )
        result = AssistantResult(
            summary=summary,
            response_type="appointment",
            urgency="routine",
            recommended_specializations=[doc_spec],
            recommended_doctor_ids=[doctor.id],
            disclaimer=DISCLAIMER,
        )
        return {"result": result, "termination": "booking_gathering_date"}

    # --- Step 3 & 4: Doctor and Date known -> Check live slots ---
    if target_date < today:
        result = AssistantResult(
            summary=f"That date ({target_date.isoformat()}) is in the past. Please choose today or an upcoming date.",
            response_type="appointment",
            urgency="routine",
            disclaimer=DISCLAIMER,
        )
        return {"result": result, "termination": "booking_invalid_date"}

    days = await slot_service.slots_for_range(db, doctor.id, target_date, target_date, now)
    free_slots = [s for s in days.get(target_date, []) if s.available]

    # Populate ctx.available_slots & ctx.appointment_options
    tz = settings.clinic_tz
    slot_options = []
    for slot in free_slots:
        ctx.available_slots.add((doctor.id, slot.starts_at.astimezone(UTC).isoformat()))
        opt = {
            "doctor_id": doctor.id,
            "doctor_name": doc_name,
            "specialization": doc_spec,
            "starts_at": slot.starts_at.isoformat(),
            "local_time": slot.starts_at.astimezone(tz).strftime("%H:%M"),
        }
        slot_options.append(opt)

    ctx.appointment_options = slot_options[:10]

    # Case 4: User authorizes booking and has selected a specific time / slot!
    if is_authorized and time_str:
        if ctx.patient is None or ctx.patient_user is None:
            result = AssistantResult(
                summary="Please sign in to the patient portal to confirm your appointment booking.",
                response_type="appointment",
                urgency="routine",
                disclaimer=DISCLAIMER,
            )
            return {"result": result, "termination": "booking_unauthenticated"}

        # Find matching free slot:
        chosen_slot = None
        if time_str:
            for s in free_slots:
                if s.starts_at.astimezone(tz).strftime("%H:%M") == time_str:
                    chosen_slot = s
                    break
        elif booking_data["is_relative_slot"] and free_slots:
            chosen_slot = free_slots[0]

        if chosen_slot is not None:
            # Execute booking!
            try:
                appointment = await appointment_service.book(
                    db,
                    ctx.patient,
                    ctx.patient_user,
                    doctor_id=doctor.id,
                    starts_at=chosen_slot.starts_at,
                    reason=None,
                )
                confirmation = {
                    "id": appointment.id,
                    "doctor_id": doctor.id,
                    "doctor_name": doc_name,
                    "starts_at": appointment.starts_at.isoformat(),
                    "status": appointment.status.value,
                }
                ctx.booked_appointment = confirmation
                ctx.appointment_options = [
                    opt
                    for opt in ctx.appointment_options
                    if not (
                        opt["doctor_id"] == doctor.id
                        and opt["starts_at"] == chosen_slot.starts_at.isoformat()
                    )
                ]
                formatted_time = chosen_slot.starts_at.astimezone(tz).strftime("%d %b %Y at %H:%M")
                summary = (
                    f"Your appointment with {doc_name} ({doc_spec}) on {formatted_time} has been successfully booked! "
                    f"(Appointment #{appointment.id}). You can review your visit in the Appointments section."
                )
                result = AssistantResult(
                    summary=summary,
                    response_type="appointment",
                    urgency="routine",
                    recommended_specializations=[doc_spec],
                    recommended_doctor_ids=[doctor.id],
                    appointment_confirmation=AppointmentConfirmation.model_validate(confirmation),
                    disclaimer=DISCLAIMER,
                )
                return {"result": result, "termination": "booking_confirmed"}
            except AppError as exc:
                summary = f"Could not book that slot: {exc.message}. Please select another time."
                result = AssistantResult(
                    summary=summary,
                    response_type="appointment",
                    urgency="routine",
                    appointment_options=[AppointmentOption.model_validate(opt) for opt in ctx.appointment_options],
                    disclaimer=DISCLAIMER,
                )
                return {"result": result, "termination": "booking_conflict"}

    # Case 3: Slots exist on that date, but user hasn't confirmed a specific time slot yet
    if free_slots:
        times_list = [s["local_time"] for s in ctx.appointment_options]
        date_str = target_date.strftime("%A, %d %B %Y")
        summary = (
            f"Here are the available appointment slots for {doc_name} on {date_str} (clinic time): "
            f"{', '.join(times_list)}. Which time works best for you? "
            f"You can reply with your preferred time (e.g. '{times_list[0]}') or click 'Book this time' below."
        )
        result = AssistantResult(
            summary=summary,
            response_type="appointment",
            urgency="routine",
            recommended_specializations=[doc_spec],
            recommended_doctor_ids=[doctor.id],
            appointment_options=[AppointmentOption.model_validate(opt) for opt in ctx.appointment_options],
            disclaimer=DISCLAIMER,
        )
        return {"result": result, "termination": "booking_offering_slots"}

    # No free slots on this date:
    summary = (
        f"There are no available appointment slots with {doc_name} on {target_date.isoformat()}. "
        f"Would you like to check another date or check other doctors in {doc_spec}?"
    )
    result = AssistantResult(
        summary=summary,
        response_type="appointment",
        urgency="routine",
        recommended_specializations=[doc_spec],
        recommended_doctor_ids=[doctor.id],
        disclaimer=DISCLAIMER,
    )
    return {"result": result, "termination": "booking_no_slots"}


async def unconfigured_node(state: HospitalGraphState) -> dict[str, Any]:
    raise ServiceUnavailableError(
        "The AI assistant is not configured on this server", code="ai_unavailable"
    )


async def llm_call_node(state: HospitalGraphState) -> dict[str, Any]:
    llm = state.get("llm")
    if llm is None:
        raise ServiceUnavailableError(
            "The AI assistant is not configured on this server", code="ai_unavailable"
        )

    tools = state["registry"].schemas()
    messages = state["messages"]
    iterations = state.get("iterations", 0) + 1
    tokens = state.get("tokens", 0)
    unknown_tool_retries = state.get("unknown_tool_retries", 0)

    try:
        response = await llm.complete(messages, tools=tools)
    except UnknownToolCallError:
        if unknown_tool_retries > 0:
            raise
        tool_traces = list(state.get("tool_traces", []))
        tool_traces.append(ToolTrace(name="<unknown>", ok=False, latency_ms=0))
        messages.append(
            {
                "role": "system",
                "content": "You may only call these tools: " + ", ".join(state["registry"].names),
            }
        )
        return {
            "iterations": iterations,
            "tokens": tokens,
            "tool_traces": tool_traces,
            "unknown_tool_retries": unknown_tool_retries + 1,
            "latest_response": None,
            "termination": "retry",
        }

    tokens += response.prompt_tokens + response.completion_tokens

    if not response.tool_calls:
        parsed = parse_result(response.content)
        return {
            "iterations": iterations,
            "tokens": tokens,
            "latest_response": response,
            "result": parsed,
            "termination": "completed" if parsed else "needs_repair",
        }

    # Record tool calls in messages:
    messages.append(
        {
            "role": "assistant",
            "content": response.content or "",
            "tool_calls": [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.name, "arguments": call.arguments},
                }
                for call in response.tool_calls
            ],
        }
    )
    return {
        "iterations": iterations,
        "tokens": tokens,
        "latest_response": response,
        "termination": "has_tool_calls",
    }


async def tools_node(state: HospitalGraphState) -> dict[str, Any]:
    response = state.get("latest_response")
    ctx = state["context"]
    registry = state["registry"]
    messages = state["messages"]
    tool_traces = list(state.get("tool_traces", []))

    if response and response.tool_calls:
        for call in response.tool_calls:
            result, trace = await registry.execute(call.name, call.arguments, ctx)
            tool_traces.append(trace)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(result, default=str),
                }
            )

    return {"tool_traces": tool_traces, "messages": messages}


async def repair_node(state: HospitalGraphState) -> dict[str, Any]:
    llm = state.get("llm")
    if llm is None:
        return {"result": None, "termination": "invalid_output"}

    messages = list(state["messages"])
    latest_response = state.get("latest_response")
    if latest_response and latest_response.content:
        messages.append({"role": "assistant", "content": latest_response.content})
    messages.append({"role": "system", "content": _FINALIZE_INSTRUCTION})

    response = await llm.complete(messages, tools=None)
    iterations = state.get("iterations", 0) + 1
    tokens = state.get("tokens", 0) + response.prompt_tokens + response.completion_tokens
    parsed = parse_result(response.content)
    return {
        "iterations": iterations,
        "tokens": tokens,
        "result": parsed,
        "termination": "repaired" if parsed else "invalid_output",
    }


async def finalize_node(state: HospitalGraphState) -> dict[str, Any]:
    ctx = state["context"]
    text = ctx.current_text
    result = state.get("result")

    if result is None:
        reason = (
            "the assistant is temporarily unavailable"
            if state.get("termination") in ("model_error", "timeout")
            else "a valid answer could not be generated"
        )
        result = safety.fallback_result(text, reason)

    # Enforce safety guardrails:
    specializations = await specialization_service.list_specializations(ctx.db, active_only=True)
    result = safety.enforce(
        result,
        patient_text=text,
        allowed_doctor_ids=ctx.seen_doctor_ids,
        known_specializations={s.name.lower(): s.name for s in specializations},
        allow_verified_prescription_details=ctx.prescription_lookup_completed,
    )

    # Attach any appointment options or bookings created during the run:
    result = result.model_copy(
        update={
            "response_type": "appointment" if ctx.appointment_options else result.response_type,
            "appointment_options": [
                AppointmentOption.model_validate(opt) for opt in ctx.appointment_options[:10]
            ],
            "appointment_confirmation": (
                AppointmentConfirmation.model_validate(ctx.booked_appointment)
                if ctx.booked_appointment
                else result.appointment_confirmation
            ),
        }
    )
    return {"result": result}


# --- Conditional edge routers ----------------------------------------------------


def route_decision(state: HospitalGraphState) -> str:
    return state.get("route", "llm_call")


def llm_next_step(state: HospitalGraphState) -> str:
    if state.get("termination") == "retry":
        return "llm_call"
    if state.get("termination") == "has_tool_calls":
        if state.get("iterations", 0) >= settings.AI_MAX_ITERATIONS or state.get("tokens", 0) >= settings.AI_MAX_TOKENS:
            return "repair"
        return "tools"
    if state.get("termination") == "needs_repair":
        return "repair"
    return "finalize"


# --- Graph Construction -----------------------------------------------------------


def build_hospital_graph() -> Any:
    workflow = StateGraph(HospitalGraphState)

    workflow.add_node("router", router_node)
    workflow.add_node("refusal", refusal_node)
    workflow.add_node("emergency", emergency_node)
    workflow.add_node("portal_help", portal_help_node)
    workflow.add_node("prescription", prescription_node)
    workflow.add_node("doctor_directory", doctor_directory_node)
    workflow.add_node("my_appointments", my_appointments_node)
    workflow.add_node("booking", booking_node)
    workflow.add_node("unconfigured", unconfigured_node)
    workflow.add_node("llm_call", llm_call_node)
    workflow.add_node("tools", tools_node)
    workflow.add_node("repair", repair_node)
    workflow.add_node("finalize", finalize_node)

    workflow.add_edge(START, "router")
    workflow.add_conditional_edges(
        "router",
        route_decision,
        {
            "refusal": "refusal",
            "emergency": "emergency",
            "portal_help": "portal_help",
            "prescription": "prescription",
            "doctor_directory": "doctor_directory",
            "my_appointments": "my_appointments",
            "booking": "booking",
            "llm_call": "llm_call",
            "unconfigured": "unconfigured",
        },
    )

    workflow.add_edge("refusal", "finalize")
    workflow.add_edge("emergency", "finalize")
    workflow.add_edge("portal_help", "finalize")
    workflow.add_edge("prescription", "finalize")
    workflow.add_edge("doctor_directory", "finalize")
    workflow.add_edge("my_appointments", "finalize")
    workflow.add_edge("booking", "finalize")

    workflow.add_conditional_edges(
        "llm_call",
        llm_next_step,
        {
            "llm_call": "llm_call",
            "tools": "tools",
            "repair": "repair",
            "finalize": "finalize",
        },
    )
    workflow.add_edge("tools", "llm_call")
    workflow.add_edge("repair", "finalize")
    workflow.add_edge("finalize", END)

    return workflow.compile()


hospital_graph = build_hospital_graph()
