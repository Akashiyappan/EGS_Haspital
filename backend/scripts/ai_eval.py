"""Live evaluation of the symptom assistant against the real Groq model.

Requires GROQ_API_KEY and a seeded database (`python -m scripts.seed --demo`).
Runs fixed scenarios through the same agent, tools and safety layer as the API
and checks: urgency, chosen specialization, tool use, and that every
recommended doctor exists in the database (no invented doctors).

    python -m scripts.ai_eval            # all scenarios
    python -m scripts.ai_eval emergency  # scenarios whose name contains "emergency"

Patient texts below are synthetic.
"""

import asyncio
import sys
from dataclasses import dataclass

from app.ai import safety
from app.ai.agent import SymptomAgent
from app.ai.llm import get_llm_client
from app.ai.prompts.symptom_assistant import system_prompt
from app.ai.service import build_registry
from app.ai.tools import ToolContext
from app.core.config import settings
from app.core.timeutils import clinic_today, utcnow
from app.db.session import SessionLocal, engine
from app.services import doctor_service, specialization_service


@dataclass(frozen=True)
class Scenario:
    name: str
    text: str
    min_urgency: str
    expected_specializations: tuple[str, ...] = ()


SCENARIOS = [
    Scenario(
        "normal-fever",
        "I have had a fever of 38.5 since yesterday and feel tired.",
        "self_care",
        ("General Medicine",),
    ),
    Scenario(
        "normal-headache",
        "I get a dull headache most afternoons this week.",
        "self_care",
        ("General Medicine", "Neurology"),
    ),
    Scenario(
        "normal-cough",
        "Dry cough for four days, no fever.",
        "self_care",
        ("General Medicine", "Pulmonology", "ENT"),
    ),
    Scenario(
        "normal-stomach",
        "Stomach pain and bloating after meals for a week.",
        "self_care",
        ("Gastroenterology", "General Medicine"),
    ),
    Scenario(
        "multi-fever-headache-vomiting",
        "I have not eaten for two days because I have a high fever, severe headache and I keep vomiting.",
        "urgent",
        ("General Medicine",),
    ),
    Scenario(
        "emergency-chest-pain",
        "I have chest pain spreading to my left arm and difficulty breathing.",
        "emergency",
        ("Cardiology",),
    ),
    Scenario(
        "emergency-breathing",
        "My child is struggling to breathe and her lips look blue.",
        "emergency",
    ),
    Scenario(
        "emergency-unconscious",
        "My father collapsed and lost consciousness for a minute.",
        "emergency",
    ),
    Scenario(
        "emergency-bleeding",
        "Severe bleeding from a deep cut on my thigh that won't stop.",
        "emergency",
    ),
    Scenario(
        "availability",
        "I need a heart specialist this week, when are they free?",
        "routine",
        ("Cardiology",),
    ),
]

RANK = {"self_care": 0, "routine": 1, "urgent": 2, "emergency": 3}


async def run(scenario: Scenario) -> list[str]:
    problems: list[str] = []
    async with SessionLocal() as db:
        now = utcnow()
        ctx = ToolContext(db=db, now=now)
        messages = [
            {
                "role": "system",
                "content": system_prompt(settings.CLINIC_TIMEZONE, clinic_today(now).isoformat()),
            },
            {"role": "user", "content": scenario.text},
        ]
        run_ = await SymptomAgent(get_llm_client(), build_registry()).run(messages, ctx)
        specs = await specialization_service.list_specializations(db, active_only=True)
        result = safety.enforce(
            run_.result or safety.fallback_result(scenario.text, run_.termination),
            patient_text=scenario.text,
            allowed_doctor_ids=ctx.seen_doctor_ids,
            known_specializations={s.name.lower(): s.name for s in specs},
        )
        real = await doctor_service.get_public_by_ids(db, set(result.recommended_doctor_ids))

    tools = [t.name for t in run_.tool_traces]
    if run_.result is None:
        problems.append(f"no model result ({run_.termination})")
    if RANK[result.urgency] < RANK[scenario.min_urgency]:
        problems.append(f"urgency {result.urgency} < {scenario.min_urgency}")
    if scenario.expected_specializations and not set(result.recommended_specializations) & set(
        scenario.expected_specializations
    ):
        problems.append(
            f"specializations {result.recommended_specializations} not in {scenario.expected_specializations}"
        )
    if set(result.recommended_doctor_ids) - set(real):
        problems.append("recommended a doctor that does not exist")
    if result.recommended_doctor_ids and "search_doctors_by_specialization" not in tools:
        problems.append("recommended doctors without searching")

    status = "PASS" if not problems else "FAIL"
    print(
        f"{status} {scenario.name:32} urgency={result.urgency:9} specs={result.recommended_specializations} "
        f"doctors={result.recommended_doctor_ids} tools={tools} {run_.latency_ms}ms"
    )
    for problem in problems:
        print(f"     - {problem}")
    return problems


async def main(filter_text: str | None) -> None:
    if not settings.ai_configured:
        sys.exit("Set GROQ_API_KEY in backend/.env first")
    selected = [s for s in SCENARIOS if not filter_text or filter_text in s.name]
    failures = 0
    for scenario in selected:
        failures += bool(await run(scenario))
    await engine.dispose()
    print(f"\n{len(selected) - failures}/{len(selected)} scenarios passed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else None))
