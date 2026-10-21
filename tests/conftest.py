"""Legacy domain tests pin historical releases; current teaching tests keep real data."""
from pathlib import Path
import tempfile
import pytest
from services import content
from tests.release_fixture import copy_legacy_content

LEGACY_DOMAIN_MODULES = {
    'test_rag_answerability_guard', 'test_rag_local_reply', 'test_rag_query', 'test_rag_routing',
    'test_rag_retrieval', 'test_rag_service', 'test_rag_v2_reply_state',
    'test_persona_rag_scope', 'test_persona_conversation_service', 'test_flagship_agent_acceptance',
    'test_game_classification_release_context', 'test_game_dialogue_persistence',
    'test_game_dialogue_projection', 'test_game_dialogue_runtime_service',
    'test_shangyang_evidence_v2',
}


@pytest.fixture(scope='module', autouse=True)
def explicit_legacy_contract_scope(request):
    if request.module.__name__.rsplit('.', 1)[-1] not in LEGACY_DOMAIN_MODULES:
        yield
        return
    original = content.content_root()
    with tempfile.TemporaryDirectory(prefix='chronovita-contract-regression-') as directory:
        root = copy_legacy_content(Path(directory) / 'content')
        content.configure(root)
        try:
            yield
        finally:
            content.configure(original)
