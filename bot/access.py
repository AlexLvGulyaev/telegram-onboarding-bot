"""Shared access control for bot commands."""

from aiogram.types import Message

from config import Settings


def is_admin(message: Message, settings: Settings) -> bool:
    """True when the message comes from ADMIN_USER_ID (RBAC single point).

    Shared by admin commands and the /topic guard (see SECURITY_NOTES).
    """
    if settings.admin_user_id is None or message.from_user is None:
        return False
    return message.from_user.id == settings.admin_user_id