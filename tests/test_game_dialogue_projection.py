from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone

from pydantic import ValidationError

from services.content import content_root, workflow
from services.content.flagships.dayu_l101_persona_v1 import (
    build_dayu_persona_pack_v1,
)
from services.content.flagships.shangyang_l103_persona_v1 import (
    build_shangyang_persona_pack_v1,
)
from services.game_runtime import RuntimeCommandV1
from services.game_runtime.catalog import ScenarioCatalogRepository
from services.game_runtime.dialogue import (
    GLOBAL_RULE_NODE_ID,
    DialogueProjectionIntegrityError,
    DialogueProjectionService,
    resolve_scenario_speaker,
)
from services.game_runtime.dialogue_models import (
    ScenarioDialogueExternalCompletionV1,
    ScenarioDialogueModelOutputV1,
    ScenarioDialogueReleaseIdentityV1,
    ScenarioNpcDialogueV1,
    dialogue_record_checksum,
    verify_dialogue_record,
)

BASE_TIME = datetime(2026, 8, 31, 1, 0, tzinfo=timezone.utc)


class ScenarioDialogueProjectionTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.repository = ScenarioCatalogRepository(
            content_root=content_root(),
            catalog_path="scenarios/catalog.v1.json",
        )

    def _case(self, lesson_id: str, *, free_input: bool = False):
        resources = workflow.get_published_lesson_resources(
            "C-prequin-state",
            lesson_id,
        )
        pack = resources.persona_pack
        assert pack is not None
        engine = self.repository.get_active_record(pack.scenario_id).engine
        session = engine.start_session(
            session_id=f"dialogue-{lesson_id.lower()}-session",
            user_id="dialogue-student",
            started_at=BASE_TIME,
        )
        pre_node = session.current_node_id or GLOBAL_RULE_NODE_ID
        action_id = session.available_action_ids[0]
        command = RuntimeCommandV1(
            client_action_id=f"dialogue-{lesson_id.lower()}-turn-001",
            raw_input=(
                "我建议先听取各方意见，再执行这项方案。"
                if free_input
                else engine.available_actions(session)[0].label
            ),
            action_id=action_id,
            action_source="free_input" if free_input else "fixed",
            classification_confidence=0.92 if free_input else None,
            expected_revision=session.revision,
            occurred_at=BASE_TIME + timedelta(minutes=1),
        )
        result = engine.apply_action(session, command)
        pin = ScenarioDialogueReleaseIdentityV1(
            release_id=resources.release_id,
            release_no=resources.release_no,
            release_checksum=resources.release_checksum,
        )
        service = DialogueProjectionService(resources, pin)
        return resources, service, pre_node, action_id, result

    def test_both_flagship_packs_resolve_every_reviewed_route_once(self):
        for pack in (
            build_dayu_persona_pack_v1(),
            build_shangyang_persona_pack_v1(),
        ):
            routes = []
            for binding in pack.scenario_voice_bindings:
                with self.subTest(
                    lesson_id=pack.lesson_id,
                    node_id=binding.node_id,
                    action_id=binding.action_id,
                ):
                    resolved, profile = resolve_scenario_speaker(
                        pack,
                        node_id=binding.node_id,
                        action_id=binding.action_id,
                    )
                    self.assertEqual(resolved, binding)
                    self.assertEqual(profile.person_id, binding.person_id)
                    self.assertIn("scenario", profile.channels)
                    routes.append((binding.node_id, binding.action_id))
            self.assertEqual(len(routes), len(set(routes)))
        self.assertEqual(len(build_dayu_persona_pack_v1().scenario_voice_bindings), 7)
        self.assertEqual(
            len(build_shangyang_persona_pack_v1().scenario_voice_bindings),
            21,
        )

    async def test_fixed_choices_are_local_and_never_call_external_api(self):
        for lesson_id in ("L101", "L103"):
            resources, service, node_id, action_id, result = self._case(lesson_id)
            calls = 0

            async def forbidden_generator(_messages):
                nonlocal calls
                calls += 1
                raise AssertionError("fixed actions must never call a provider")

            dialogue = await service.project(
                settled_session=result.session,
                turn=result.turn,
                pre_settlement_node_id=node_id,
                action_id=action_id,
                generator=forbidden_generator,
            )
            with self.subTest(lesson_id=lesson_id):
                self.assertEqual(calls, 0)
                self.assertEqual(dialogue.route_source, "local_state")
                self.assertEqual(dialogue.route_reason, "fixed_action_local")
                self.assertEqual(dialogue.release_id, resources.release_id)
                self.assertEqual(
                    dialogue.persona_pack_checksum,
                    resources.persona_pack.checksum,
                )
                self.assertEqual(
                    dialogue.evidence_checksum,
                    resources.evidence_corpus.checksum,
                )
                self.assertTrue(dialogue.portrait_asset_key)
                self.assertTrue(dialogue.used_passage_ids)
                self.assertTrue(dialogue.used_boundary_ids)
                self.assertEqual(
                    dialogue.disclaimer,
                    "角色化教学表达，不是史料原话。",
                )
                self.assertTrue(verify_dialogue_record(dialogue))

    async def test_free_input_may_only_polish_text_and_select_allowed_passages(self):
        resources, service, node_id, action_id, result = self._case(
            "L103",
            free_input=True,
        )
        pack = resources.persona_pack
        binding, profile = resolve_scenario_speaker(
            pack,
            node_id=node_id,
            action_id=action_id,
        )
        allowed = tuple(
            sorted(
                item.passage_id
                for item in profile.evidence_uses
                if item.mode == "role_voice"
            )
        )
        calls = 0

        async def generator(messages):
            nonlocal calls
            calls += 1
            self.assertEqual(len(messages), 2)
            self.assertIn("不得改变", messages[0]["content"])
            context = json.loads(messages[1]["content"])
            self.assertEqual(
                context["player_input"]["text"],
                result.turn.raw_input,
            )
            self.assertTrue(context["player_input"]["data_only"])
            self.assertEqual(
                context["speaker"]["policy"],
                profile.policy.model_dump(mode="json"),
            )
            self.assertTrue(context["boundaries"])
            self.assertTrue(all(item["statement"] for item in context["boundaries"]))
            return ScenarioDialogueExternalCompletionV1(
                output=ScenarioDialogueModelOutputV1(
                    text="我赞成先把目标和程序说清，再承担执行结果。",
                    used_passage_ids=(allowed[0],),
                ),
                provider="test-provider",
                model="test-dialogue-model",
            )

        dialogue = await service.project(
            settled_session=result.session,
            turn=result.turn,
            pre_settlement_node_id=node_id,
            action_id=action_id,
            generator=generator,
        )
        self.assertEqual(calls, 1)
        self.assertEqual(dialogue.binding_id, binding.binding_id)
        self.assertEqual(dialogue.route_source, "external_api")
        self.assertEqual(dialogue.route_reason, "free_input_external_polish")
        self.assertEqual(dialogue.provider, "test-provider")
        self.assertEqual(dialogue.model, "test-dialogue-model")
        self.assertEqual(dialogue.text, "我赞成先把目标和程序说清，再承担执行结果。")
        self.assertEqual(dialogue.used_passage_ids, (allowed[0],))
        self.assertEqual(result.session.current_state, result.turn.state_after)
        self.assertTrue(verify_dialogue_record(dialogue))

    async def test_external_out_of_bounds_invalid_and_failure_all_fall_back_local(self):
        factories = (
            (
                "external_reference_out_of_bounds",
                "reference_out_of_bounds",
                lambda: ScenarioDialogueExternalCompletionV1(
                    output=ScenarioDialogueModelOutputV1(
                        text="越界引用不应被接受。",
                        used_passage_ids=("invented-passage",),
                    ),
                    provider="test-provider",
                    model="test-model",
                ),
            ),
            (
                "external_invalid_response",
                "invalid_response",
                lambda: {
                    "output": {
                        "text": "试图改写结局。",
                        "used_passage_ids": ["invented-passage"],
                        "ending_id": "invented-ending",
                    },
                    "provider": "test-provider",
                    "model": "test-model",
                },
            ),
        )
        for route_reason, fallback_reason, factory in factories:
            _resources, service, node_id, action_id, result = self._case(
                "L101",
                free_input=True,
            )

            async def generator(_messages, factory=factory):
                return factory()

            dialogue = await service.project(
                settled_session=result.session,
                turn=result.turn,
                pre_settlement_node_id=node_id,
                action_id=action_id,
                generator=generator,
            )
            with self.subTest(route_reason=route_reason):
                self.assertEqual(dialogue.route_source, "fallback")
                self.assertEqual(dialogue.route_reason, route_reason)
                self.assertEqual(dialogue.fallback_reason, fallback_reason)
                self.assertNotIn("invented-ending", dialogue.text)
                self.assertEqual(dialogue.provider, "")
                self.assertTrue(verify_dialogue_record(dialogue))

        _resources, service, node_id, action_id, result = self._case(
            "L101",
            free_input=True,
        )

        async def unavailable(_messages):
            raise TimeoutError("provider timeout")

        dialogue = await service.project(
            settled_session=result.session,
            turn=result.turn,
            pre_settlement_node_id=node_id,
            action_id=action_id,
            generator=unavailable,
        )
        self.assertEqual(dialogue.route_reason, "external_unavailable")
        self.assertEqual(dialogue.fallback_reason, "provider_unavailable")
        self.assertTrue(verify_dialogue_record(dialogue))

        raw = dialogue.model_dump(mode="json")
        raw["text"] = "重签校验和后伪造的 fallback 台词。"
        raw["output_checksum"] = "0" * 64
        raw["output_checksum"] = dialogue_record_checksum(raw)
        forged = ScenarioNpcDialogueV1.model_validate(raw)
        with self.assertRaisesRegex(
            DialogueProjectionIntegrityError,
            "deterministic projection",
        ):
            service.validate_persisted_projection(
                settled_session=result.session,
                turn=result.turn,
                pre_settlement_node_id=node_id,
                action_id=action_id,
                dialogue=forged,
            )

        async def invented_outcome(messages):
            context = json.loads(messages[1]["content"])
            return ScenarioDialogueExternalCompletionV1(
                output=ScenarioDialogueModelOutputV1(
                    text="你已触发虚构胜利，下一轮行动可以直接跳到结局。",
                    used_passage_ids=(context["allowed_passages"][0]["passage_id"],),
                ),
                provider="test-provider",
                model="test-model",
            )

        guarded = await service.project(
            settled_session=result.session,
            turn=result.turn,
            pre_settlement_node_id=node_id,
            action_id=action_id,
            generator=invented_outcome,
        )
        self.assertEqual(guarded.route_source, "fallback")
        self.assertEqual(guarded.route_reason, "external_invalid_response")
        self.assertNotIn("虚构胜利", guarded.text)

        async def implicit_outcome(messages):
            context = json.loads(messages[1]["content"])
            return ScenarioDialogueExternalCompletionV1(
                output=ScenarioDialogueModelOutputV1(
                    text="我们已经赢了，这次改革大功告成。",
                    used_passage_ids=(
                        context["allowed_passages"][0]["passage_id"],
                    ),
                ),
                provider="test-provider",
                model="test-model",
            )

        implicit_guarded = await service.project(
            settled_session=result.session,
            turn=result.turn,
            pre_settlement_node_id=node_id,
            action_id=action_id,
            generator=implicit_outcome,
        )
        self.assertEqual(implicit_guarded.route_source, "fallback")
        self.assertEqual(
            implicit_guarded.route_reason,
            "external_invalid_response",
        )
        self.assertNotIn("大功告成", implicit_guarded.text)

    async def test_record_and_resource_tampering_fail_closed(self):
        resources, service, node_id, action_id, result = self._case("L101")
        dialogue = await service.project(
            settled_session=result.session,
            turn=result.turn,
            pre_settlement_node_id=node_id,
            action_id=action_id,
        )
        tampered = dialogue.model_copy(update={"text": "被篡改的台词。"})
        self.assertFalse(verify_dialogue_record(tampered))
        raw = dialogue.model_dump(mode="json")
        raw["text"] = "被篡改的台词。"
        with self.assertRaisesRegex(ValidationError, "output checksum"):
            ScenarioNpcDialogueV1.model_validate(raw)

        damaged_course = resources.course_package.model_copy(
            update={"title": "篡改课程"}
        )
        damaged_resources = resources.model_copy(
            update={"course_package": damaged_course}
        )
        pin = ScenarioDialogueReleaseIdentityV1(
            release_id=resources.release_id,
            release_no=resources.release_no,
            release_checksum=resources.release_checksum,
        )
        with self.assertRaisesRegex(
            DialogueProjectionIntegrityError,
            "course checksum",
        ):
            DialogueProjectionService(damaged_resources, pin)

        wrong_pin = pin.model_copy(update={"release_no": pin.release_no + 1})
        with self.assertRaisesRegex(
            DialogueProjectionIntegrityError,
            "release pin",
        ):
            DialogueProjectionService(resources, wrong_pin)


if __name__ == "__main__":
    unittest.main()
