from uuid import UUID

from shopping.config import get_settings


def get_owner_id() -> UUID:
    """Return the stable local owner; request data never chooses an owner."""
    return get_settings().local_owner_id
