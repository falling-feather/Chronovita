from __future__ import annotations

import threading

from sqlalchemy.engine import Engine

from .models import (
    MAX_CONVERSATION_TURNS,
    MAX_CURRENT_EVIDENCE_PASSAGES,
    RECENT_CONTEXT_TURNS,
    PersonaConversationContextV1,
    PersonaConversationIdentityV1,
    PersonaConversationTurnInputV1,
    PersonaConversationTurnV1,
    PersonaConversationV1,
    calculate_persona_conversation_checksum,
    conversation_turn_input_checksum,
    new_persona_conversation,
)
from .service import (
    PersonaConversationBindingInvalid,
    PersonaConversationCoordinator,
    PersonaConversationMessageResult,
    PersonaConversationPersonUnavailable,
    PersonaConversationReleaseChanged,
    PersonaConversationReleaseUnavailable,
)
from .store import (
    MAX_CONVERSATION_RECORD_BYTES,
    MAX_CONVERSATION_TURN_BYTES,
    PersonaConversationAlreadyExists,
    PersonaConversationAppendResult,
    PersonaConversationConflict,
    PersonaConversationIntegrityError,
    PersonaConversationLimitReached,
    PersonaConversationNotFound,
    PersonaConversationStore,
    PersonaConversationStoreError,
    PersonaConversationWriteConflict,
    PersonaMessageIdConflict,
    StoredPersonaConversationRecord,
    decode_persona_conversation,
    encode_persona_conversation,
    persona_conversations_table,
)

_LOCK = threading.RLock()
_STORE: PersonaConversationStore | None = None


def configure_persona_conversations(engine: Engine) -> PersonaConversationStore:
    global _STORE
    with _LOCK:
        if _STORE is not None and _STORE.engine is not engine:
            raise RuntimeError("persona conversation store is already configured")
        if _STORE is None:
            _STORE = PersonaConversationStore(engine)
        return _STORE


def get_persona_conversations() -> PersonaConversationStore:
    with _LOCK:
        if _STORE is None:
            raise RuntimeError("persona conversation store is not configured")
        return _STORE


def shutdown_persona_conversations() -> None:
    global _STORE
    with _LOCK:
        _STORE = None


__all__ = [
    "MAX_CONVERSATION_RECORD_BYTES",
    "MAX_CONVERSATION_TURNS",
    "MAX_CONVERSATION_TURN_BYTES",
    "MAX_CURRENT_EVIDENCE_PASSAGES",
    "RECENT_CONTEXT_TURNS",
    "PersonaConversationAlreadyExists",
    "PersonaConversationAppendResult",
    "PersonaConversationBindingInvalid",
    "PersonaConversationConflict",
    "PersonaConversationCoordinator",
    "PersonaConversationContextV1",
    "PersonaConversationIdentityV1",
    "PersonaConversationIntegrityError",
    "PersonaConversationLimitReached",
    "PersonaConversationMessageResult",
    "PersonaConversationNotFound",
    "PersonaConversationPersonUnavailable",
    "PersonaConversationReleaseChanged",
    "PersonaConversationReleaseUnavailable",
    "PersonaConversationStore",
    "PersonaConversationStoreError",
    "PersonaConversationTurnInputV1",
    "PersonaConversationTurnV1",
    "PersonaConversationV1",
    "PersonaConversationWriteConflict",
    "PersonaMessageIdConflict",
    "StoredPersonaConversationRecord",
    "calculate_persona_conversation_checksum",
    "configure_persona_conversations",
    "conversation_turn_input_checksum",
    "decode_persona_conversation",
    "encode_persona_conversation",
    "get_persona_conversations",
    "new_persona_conversation",
    "persona_conversations_table",
    "shutdown_persona_conversations",
]
