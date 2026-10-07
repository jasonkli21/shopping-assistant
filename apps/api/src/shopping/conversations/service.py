"""Conversation domain service facade.

The implementation is split by persistence boundary: commands, history,
generation lifecycle, and proposal mutations each live in focused modules.
"""

from .commands import MessageCommandResult, create_message_command
from .generation import (
    claim_expired_generations,
    complete_generation,
    fail_generation,
    heartbeat_generation,
    interrupt_generation,
    load_generation_input,
)
from .history import get_message_for_stream, list_conversations, list_messages
from .proposals import apply_proposal, dismiss_proposal

__all__ = [
    "MessageCommandResult",
    "apply_proposal",
    "complete_generation",
    "claim_expired_generations",
    "create_message_command",
    "dismiss_proposal",
    "fail_generation",
    "get_message_for_stream",
    "heartbeat_generation",
    "interrupt_generation",
    "list_conversations",
    "list_messages",
    "load_generation_input",
]
