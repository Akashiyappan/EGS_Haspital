"""AI symptom assistant.

    API route -> AIService -> SymptomAgent -> ToolRegistry -> tools -> domain services -> DB

The model never touches the database or SQL: it can only call the read-only
tools registered in `tools/`, whose arguments are validated before execution.
Safety rules that must hold regardless of model behaviour (emergency
escalation, no invented doctors, fixed disclaimer) are enforced in code by
`safety.py` after the model responds.
"""
