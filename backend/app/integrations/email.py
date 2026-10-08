"""Email delivery abstraction. Business code depends on `EmailSender` only, so a
real provider (SES, SendGrid, SMTP) can be added without touching services."""

import logging
from dataclasses import dataclass
from typing import Protocol

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    text: str


class EmailSender(Protocol):
    async def send(self, message: EmailMessage) -> None: ...


class ConsoleEmailSender:
    """Development backend: logs that an email would be sent, never its body
    (bodies may contain reset links). In ENVIRONMENT=local the body is logged at
    DEBUG so developers can follow reset links."""

    async def send(self, message: EmailMessage) -> None:
        domain = message.to.rpartition("@")[2]
        logger.info("Email queued (console backend) to=*@%s subject=%r", domain, message.subject)
        if settings.ENVIRONMENT == "local":
            logger.debug("Email body for local development:\n%s", message.text)


class DisabledEmailSender:
    async def send(self, message: EmailMessage) -> None:
        return None


def get_email_sender() -> EmailSender:
    if settings.EMAIL_BACKEND == "console":
        return ConsoleEmailSender()
    return DisabledEmailSender()
