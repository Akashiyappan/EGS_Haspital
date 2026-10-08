import json
from typing import Any

from app.ai.llm import LLMResponse, ToolCall
from app.integrations.storage import StoredImage

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 256
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 256


class FakeStorage:
    """In-memory stand-in for Cloudinary."""

    def __init__(self) -> None:
        self.uploads: list[dict[str, Any]] = []
        self.deleted: list[str] = []

    async def upload_image(
        self, data: bytes, *, folder: str, content_type: str, private: bool
    ) -> StoredImage:
        public_id = f"onezae/{folder}/img{len(self.uploads) + 1}"
        delivery = "authenticated" if private else "upload"
        self.uploads.append({"public_id": public_id, "private": private, "bytes": len(data)})
        return StoredImage(
            public_id=public_id,
            delivery_type=delivery,
            url=self.url_for(public_id, delivery, "png"),
            content_type=content_type,
            format="png",
            bytes=len(data),
            width=10,
            height=10,
        )

    async def delete(self, public_id: str, delivery_type: str) -> None:
        self.deleted.append(public_id)

    def url_for(self, public_id: str, delivery_type: str, fmt: str | None) -> str:
        return f"https://res.cloudinary.test/image/{delivery_type}/s--sig--/{public_id}.{fmt}"


class FakeLLM:
    """Scripted LLM. Queue responses (or exceptions) with `script()`; every call
    is recorded with the messages and tools it received."""

    def __init__(self) -> None:
        self.responses: list[LLMResponse | Exception] = []
        self.calls: list[dict[str, Any]] = []

    def script(self, *responses: LLMResponse | Exception) -> None:
        self.responses.extend(responses)

    async def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None,
        tool_choice: str = "auto",
    ) -> LLMResponse:
        self.calls.append({"messages": [dict(m) for m in messages], "tools": tools})
        if not self.responses:
            raise AssertionError("FakeLLM called more times than scripted")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def tool_call(name: str, arguments: dict[str, Any], call_id: str = "call_1") -> LLMResponse:
    return LLMResponse(
        content=None,
        tool_calls=[ToolCall(id=call_id, name=name, arguments=json.dumps(arguments))],
        prompt_tokens=100,
        completion_tokens=20,
    )


def final_answer(**fields: Any) -> LLMResponse:
    payload = {
        "summary": "General information about your symptoms.",
        "urgency": "routine",
        "possible_concerns": [],
        "recommended_specializations": [],
        "recommended_doctor_ids": [],
        "next_steps": [],
        "follow_up_questions": [],
        **fields,
    }
    return LLMResponse(content=json.dumps(payload), prompt_tokens=200, completion_tokens=80)
