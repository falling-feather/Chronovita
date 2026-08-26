import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from main import app
from settings import settings
from services import content, persistence
from services.contracts.v1 import (
    DossierV1,
    course_package_from_legacy,
    verify_contract_checksum,
)
from services.game_runtime.service import shutdown_game_runtime


class DayuEndToEndTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.content_root = Path(self.temp_dir.name) / "content"
        shutil.copytree(REPO_ROOT / "content", self.content_root)
        self.previous = {
            "content_root": settings.content_root,
            "game_catalog_path": settings.game_catalog_path,
            "game_user_id": settings.game_user_id,
            "sqlite_path": settings.sqlite_path,
            "admin_token": settings.admin_token,
            "admin_actor": settings.admin_actor,
            "llm_provider": settings.llm_provider,
            "deepseek_api_key": settings.deepseek_api_key,
            "auth_mode": settings.auth_mode,
        }
        settings.content_root = str(self.content_root)
        settings.game_catalog_path = "scenarios/catalog.v1.json"
        settings.game_user_id = "dayu-e2e-student"
        settings.sqlite_path = str(Path(self.temp_dir.name) / "chronovita.db")
        settings.admin_token = "dayu-e2e-admin"
        settings.admin_actor = "dayu-e2e-reviewer"
        settings.llm_provider = "mock"
        settings.deepseek_api_key = ""
        settings.auth_mode = "legacy-local"
        self.headers = {"X-Admin-Token": settings.admin_token}
        persistence.close_engine()
        shutdown_game_runtime()

    def tearDown(self):
        shutdown_game_runtime()
        persistence.close_engine()
        for key, value in self.previous.items():
            setattr(settings, key, value)
        content.configure()
        self.temp_dir.cleanup()

    def test_teacher_publish_to_dossier_canvas_and_restart_replay(self):
        with TestClient(app) as first_client:
            self._save_review_and_seal_course(first_client)
            sealed = content.get_sealed_package("dayu-e2e", 1)
            runtime_course = course_package_from_legacy(sealed)
            fact_ids = [item.fact_id for item in runtime_course.facts]
            source_id = runtime_course.source_refs[0].source_id

            scenario = self._save_validate_and_seal_scenario(
                first_client,
                fact_ids=fact_ids,
                source_id=source_id,
            )
            descriptor = scenario["record"]["descriptor"]
            release = self._response_json(
                first_client.post(
                    "/api/v1/admin/content/sealed/dayu-e2e/versions/1/publish",
                    headers=self.headers,
                    json={
                        "scenarios": [
                            {
                                "scenario_id": descriptor["artifact_id"],
                                "scenario_version": descriptor["version"],
                                "scenario_checksum": descriptor["checksum"],
                                "primary": True,
                            }
                        ]
                    },
                )
            )["release"]
            self.assertEqual(release["schema_version"], "course-release/v2")

            lesson = self._response_json(
                first_client.get("/api/v1/courses/C-dayu-e2e/lessons/dayu-e2e")
            )
            self.assertEqual(lesson["release_id"], release["release_id"])
            self.assertEqual(lesson["primary_scenario_id"], "scenario-dayu-e2e")
            self.assertEqual(len(lesson["scenario_refs"]), 1)
            release_pin = self._release_pin(lesson)

            start_request = {
                "scenario_id": "scenario-dayu-e2e",
                "client_request_id": "dayu-e2e-start-001",
                "release_pin": release_pin,
            }
            missing_pin = first_client.post(
                "/api/v1/practice/game/sessions",
                json={
                    "scenario_id": "scenario-dayu-e2e",
                    "client_request_id": "dayu-e2e-missing-pin-001",
                },
            )
            self.assertEqual(missing_pin.status_code, 409, missing_pin.text)
            self.assertEqual(
                missing_pin.json()["detail"]["code"],
                "published_scenario_pin_required",
            )
            started = self._response_json(
                first_client.post(
                    "/api/v1/practice/game/sessions",
                    json=start_request,
                )
            )
            self.assertEqual(started["scenario"]["audience"], "published")
            self.assertEqual(started["scenario"]["release_id"], release["release_id"])
            session = started["session"]
            session_id = session["session_id"]
            self.assertEqual(session["revision"], 1)
            dossier_not_ready = first_client.get(
                f"/api/v1/practice/game/sessions/{session_id}/dossier"
            )
            self.assertEqual(dossier_not_ready.status_code, 409, dossier_not_ready.text)
            self.assertEqual(
                dossier_not_ready.json()["detail"]["code"],
                "dossier_not_ready",
            )

            unavailable = self._response_json(
                first_client.post(
                    f"/api/v1/practice/game/sessions/{session_id}/free-input",
                    json={
                        "client_action_id": "dayu-e2e-semantic-001",
                        "raw_input": "我想先沿河走一圈，再决定怎么治水",
                        "expected_revision": 1,
                    },
                )
            )
            self.assertEqual(unavailable["kind"], "provider_unavailable")
            self.assertEqual(unavailable["reason_code"], "fact_context_unavailable")
            unchanged = self._response_json(
                first_client.get(f"/api/v1/practice/game/sessions/{session_id}")
            )
            self.assertEqual(unchanged["revision"], 1)
            self.assertEqual(unchanged["turns"], [])

            exact = self._response_json(
                first_client.post(
                    f"/api/v1/practice/game/sessions/{session_id}/free-input",
                    json={
                        "client_action_id": "dayu-e2e-free-001",
                        "raw_input": "勘察河道",
                        "expected_revision": 1,
                    },
                )
            )
            self.assertEqual(exact["kind"], "advanced")
            self.assertEqual(exact["result"]["turn"]["action_source"], "free_input")
            self.assertEqual(
                exact["result"]["turn"]["classification_evidence"]["source"],
                "exact",
            )
            session = exact["result"]["session"]

            for action_no, action_id in enumerate(
                ("explain-plan", "open-channels", "open-channels"),
                start=2,
            ):
                advanced = self._response_json(
                    first_client.post(
                        f"/api/v1/practice/game/sessions/{session_id}/turns",
                        json={
                            "client_action_id": f"dayu-e2e-fixed-{action_no:03d}",
                            "action_id": action_id,
                            "expected_revision": session["revision"],
                        },
                    )
                )
                session = advanced["session"]

            self.assertEqual(session["status"], "completed")
            self.assertEqual(session["current_turn"], 4)
            self.assertEqual(session["ending_id"], "ending-water-controlled")
            self.assertIsNotNone(session["dossier_id"])

            dossier_json = self._response_json(
                first_client.get(
                    f"/api/v1/practice/game/sessions/{session_id}/dossier"
                )
            )
            dossier = DossierV1.model_validate(dossier_json)
            self.assertTrue(verify_contract_checksum(dossier))
            self.assertEqual(dossier.session_id, session_id)
            self.assertEqual(len(dossier.key_choices), 4)
            self.assertEqual(len(dossier.knowledge_nodes), len(fact_ids))
            self.assertEqual(dossier.follow_up_questions, [
                "哪一次选择改变了治水方法？",
                "工程收益与社会代价应如何一起解释？",
            ])

            replay_json = self._response_json(
                first_client.get(
                    f"/api/v1/practice/game/sessions/{session_id}/replay"
                )
            )
            self.assertTrue(replay_json["verified"])
            self.assertEqual(len(replay_json["commands"]), 4)
            self.assertEqual(replay_json["session"], session)

            canvas_nodes = [
                {
                    "id": "student:dayu-e2e-note",
                    "position": {"x": 40, "y": 40},
                    "data": {"label": "我的治水复盘"},
                },
                *[
                    {
                        "id": f"dossier:{dossier.course_checksum}:node:{item.node_id}",
                        "position": {"x": 80 + index * 220, "y": 220},
                        "data": {
                            "label": item.label,
                            "dossier_kind": item.kind,
                            "source_ref_ids": item.source_ref_ids,
                            "dossier_id": dossier.dossier_id,
                            "session_id": dossier.session_id,
                            "dossier_checksum": dossier.checksum,
                        },
                    }
                    for index, item in enumerate(dossier.knowledge_nodes)
                ],
            ]
            saved_canvas = self._response_json(
                first_client.put(
                    "/api/v1/practice/canvas/dayu-e2e",
                    json={
                        "expected_revision": 0,
                        "nodes": canvas_nodes,
                        "edges": [],
                    },
                )
            )
            self.assertEqual(saved_canvas["revision"], 1)
            stale = first_client.put(
                "/api/v1/practice/canvas/dayu-e2e",
                json={"expected_revision": 0, "nodes": [], "edges": []},
            )
            self.assertEqual(stale.status_code, 409, stale.text)
            self.assertEqual(
                stale.json()["detail"]["code"],
                "canvas_revision_conflict",
            )
            authoritative_canvas = self._response_json(
                first_client.get("/api/v1/practice/canvas/dayu-e2e")
            )
            self.assertEqual(authoritative_canvas["nodes"], canvas_nodes)

        with TestClient(app) as restarted_client:
            resumed = self._response_json(
                restarted_client.post(
                    "/api/v1/practice/game/sessions",
                    json=start_request,
                )
            )
            self.assertEqual(resumed["session"], session)
            self.assertEqual(resumed["session"]["session_id"], session_id)

            recovered_dossier = self._response_json(
                restarted_client.get(
                    f"/api/v1/practice/game/sessions/{session_id}/dossier"
                )
            )
            self.assertEqual(recovered_dossier, dossier_json)
            recovered_replay = self._response_json(
                restarted_client.get(
                    f"/api/v1/practice/game/sessions/{session_id}/replay"
                )
            )
            self.assertTrue(recovered_replay["verified"])
            self.assertEqual(recovered_replay["session"], session)

            recovered_canvas = self._response_json(
                restarted_client.get("/api/v1/practice/canvas/dayu-e2e")
            )
            self.assertTrue(recovered_canvas["found"])
            self.assertEqual(recovered_canvas["revision"], 1)
            self.assertEqual(recovered_canvas["nodes"], canvas_nodes)

            revised_canvas_nodes = [
                *canvas_nodes,
                {
                    "id": "student:dayu-e2e-restart-note",
                    "position": {"x": 40, "y": 420},
                    "data": {"label": "重启后补充"},
                },
            ]
            revised_canvas = self._response_json(
                restarted_client.put(
                    "/api/v1/practice/canvas/dayu-e2e",
                    json={
                        "expected_revision": 1,
                        "nodes": revised_canvas_nodes,
                        "edges": [],
                    },
                )
            )
            self.assertEqual(revised_canvas["revision"], 2)
            restart_stale = restarted_client.put(
                "/api/v1/practice/canvas/dayu-e2e",
                json={"expected_revision": 1, "nodes": [], "edges": []},
            )
            self.assertEqual(restart_stale.status_code, 409, restart_stale.text)
            after_restart_conflict = self._response_json(
                restarted_client.get("/api/v1/practice/canvas/dayu-e2e")
            )
            self.assertEqual(after_restart_conflict["revision"], 2)
            self.assertEqual(after_restart_conflict["nodes"], revised_canvas_nodes)

            recovered_lesson = self._response_json(
                restarted_client.get(
                    "/api/v1/courses/C-dayu-e2e/lessons/dayu-e2e"
                )
            )
            self.assertEqual(recovered_lesson["release_id"], release["release_id"])

    def _save_review_and_seal_course(self, client: TestClient) -> None:
        payload = content.content_template().model_dump(mode="json")
        payload.update(
            {
                "lesson_id": "dayu-e2e",
                "course_id": "C-dayu-e2e",
                "course_title": "大禹治水整链验收课程",
                "title": "大禹治水：疏堵与协作",
                "unit": "文明起源与公共协作",
                "era": "传说时代",
                "body": [
                    "治水方案需要同时观察水势、地形与可用资源。",
                    "长期工程既改变水患风险，也消耗粮食、劳力与民众承受度。",
                    "跨群体解释方案并形成协作，是持续推进工程的重要条件。",
                ],
                "abstract": "以治水方法、资源代价和公共协作为线索的技术验收样板。",
                "keywords": [
                    {"word": "治水", "gloss": "组织工程与社会行动应对水患。"},
                    {"word": "疏导", "gloss": "依据地势引导水流的教学模型。"},
                    {"word": "协作", "gloss": "不同群体协调资源与行动。"},
                ],
                "people": [
                    {
                        "name": "禹",
                        "role": "治水行动组织者",
                        "summary": "在样板局势中组织勘察、工程投入与群体协作。",
                        "persona": "重视勘察、方法调整和长期协作。",
                        "boundaries": ["不把传说细节表述成无争议的考古定论。"],
                    }
                ],
                "map_points": [
                    {
                        "label": "黄河中游教学点",
                        "region": "黄河中游",
                        "note": "技术样板位置，不代表精确历史坐标。",
                        "kind": "teaching-placeholder",
                    }
                ],
                "source_refs": [
                    {
                        "title": "大禹治水整链验收资料",
                        "source": "Chronovita QA fixture",
                        "citation_note": "仅用于验证系统链路，不承担正式教学结论。",
                        "reliability": "reviewed",
                    }
                ],
                "facts": [
                    "治水方法的选择会改变短期风险与长期工程效果。",
                    "持续工程会消耗粮食和劳力，并影响民众承受度。",
                    "跨群体协作会影响工程可持续推进的条件。",
                ],
                "qa_points": ["为什么治水不能只比较工程速度？"],
                "level_goals": ["依据状态变化解释工程收益、资源代价与协作条件。"],
                "teacher_notes": "自动化验收夹具，正式内容仍须教师审校。",
            }
        )
        self._response_json(
            client.post(
                "/api/v1/admin/content/drafts",
                headers=self.headers,
                json=payload,
            )
        )
        validated = self._response_json(
            client.post(
                "/api/v1/admin/content/drafts/dayu-e2e/validate",
                headers=self.headers,
                json={},
            )
        )
        self.assertTrue(validated["report"]["valid"], validated["report"])
        for suffix, body in (
            ("submit-review", {"note": "进入整链验收审校。"}),
            ("review", {"decision": "approve", "note": "技术字段已核对。"}),
            ("seal", {}),
        ):
            self._response_json(
                client.post(
                    f"/api/v1/admin/content/drafts/dayu-e2e/{suffix}",
                    headers=self.headers,
                    json=body,
                )
            )

    def _save_validate_and_seal_scenario(
        self,
        client: TestClient,
        *,
        fact_ids: list[str],
        source_id: str,
    ) -> dict:
        payload = self._response_json(
            client.get(
                "/api/v1/admin/content/scenario-drafts/template",
                headers=self.headers,
            )
        )
        payload.update(
            {
                "scenario_id": "scenario-dayu-e2e",
                "course_id": "C-dayu-e2e",
                "lesson_id": "dayu-e2e",
                "title": "大禹治水：疏堵与协作",
                "student_role": "协助组织治水的行动者",
                "objective": "在五回合内降低水患并保留公共协作基础。",
                "opening": "汛期将近，你需要先理解地势，再组织工程与协作。",
                "max_turns": 5,
                "variables": [
                    {
                        "variable_id": "flood_risk",
                        "label": "水患",
                        "initial": 70,
                        "minimum": 0,
                        "maximum": 100,
                    },
                    {
                        "variable_id": "engineering_knowledge",
                        "label": "工程认知",
                        "initial": 35,
                        "minimum": 0,
                        "maximum": 100,
                    },
                    {
                        "variable_id": "public_support",
                        "label": "民心",
                        "initial": 50,
                        "minimum": 0,
                        "maximum": 100,
                    },
                ],
                "npcs": [],
                "action_rules": [
                    {
                        "action_id": "survey-terrain",
                        "label": "勘察地势",
                        "aliases": ["勘察河道"],
                        "effects": [
                            {
                                "kind": "state",
                                "variable_id": "engineering_knowledge",
                                "operation": "add",
                                "value": 15,
                            },
                            {
                                "kind": "state",
                                "variable_id": "flood_risk",
                                "operation": "add",
                                "value": 5,
                            },
                        ],
                        "feedback": "工程认知提升，但勘察期间水患仍在发展。",
                        "fact_refs": [fact_ids[0]],
                    },
                    {
                        "action_id": "explain-plan",
                        "label": "解释治水计划",
                        "effects": [
                            {
                                "kind": "state",
                                "variable_id": "public_support",
                                "operation": "add",
                                "value": 15,
                            }
                        ],
                        "feedback": "解释方案提高了协作意愿。",
                        "fact_refs": [fact_ids[2]],
                    },
                    {
                        "action_id": "open-channels",
                        "label": "开挖疏导线",
                        "available_when": [
                            {
                                "kind": "state",
                                "variable_id": "engineering_knowledge",
                                "operator": "gte",
                                "value": 50,
                            }
                        ],
                        "effects": [
                            {
                                "kind": "state",
                                "variable_id": "flood_risk",
                                "operation": "add",
                                "value": -25,
                            },
                            {
                                "kind": "state",
                                "variable_id": "engineering_knowledge",
                                "operation": "add",
                                "value": 10,
                            },
                        ],
                        "feedback": "疏导降低水患，同时要求持续投入。",
                        "fact_refs": fact_ids[:2],
                    },
                ],
                "event_rules": [],
                "ending_rules": [
                    {
                        "ending_id": "ending-water-controlled",
                        "title": "疏导见效",
                        "conditions": [
                            {"kind": "turn", "operator": "gte", "value": 4},
                            {
                                "kind": "state",
                                "variable_id": "flood_risk",
                                "operator": "lte",
                                "value": 35,
                            },
                            {
                                "kind": "state",
                                "variable_id": "engineering_knowledge",
                                "operator": "gte",
                                "value": 60,
                            },
                        ],
                        "summary": "你以勘察、疏导和协作逐步控制了水患。",
                        "historical_explanation": "治水决策需要把工程方法、资源与社会协作放在同一局势中理解。",
                        "major_costs": ["前期勘察的短期风险", "持续工程的资源投入"],
                        "source_ref_ids": [source_id],
                        "fact_refs": fact_ids,
                        "priority": 10,
                    },
                    {
                        "ending_id": "ending-timeout",
                        "title": "汛期未决",
                        "conditions": [
                            {"kind": "turn", "operator": "gte", "value": 5}
                        ],
                        "summary": "五回合后仍未控制水患。",
                        "historical_explanation": "技术兜底结局。",
                        "priority": 1000,
                    },
                ],
                "fact_refs": fact_ids,
                "source_ref_ids": [source_id],
                "dossier_template": {
                    "title_template": "《{scenario_title}卷宗》",
                    "reflection_questions": [
                        "哪一次选择改变了治水方法？",
                        "工程收益与社会代价应如何一起解释？",
                    ],
                    "knowledge_node_kinds": ["cause", "consequence", "concept"],
                },
            }
        )
        self._response_json(
            client.post(
                "/api/v1/admin/content/scenario-drafts",
                headers=self.headers,
                json=payload,
            )
        )
        validated = self._response_json(
            client.post(
                "/api/v1/admin/content/scenario-drafts/scenario-dayu-e2e/validate",
                headers=self.headers,
            )
        )
        self.assertTrue(validated["report"]["valid"])
        sealed = self._response_json(
            client.post(
                "/api/v1/admin/content/scenario-drafts/scenario-dayu-e2e/seal",
                headers=self.headers,
            )
        )
        self.assertFalse(sealed["idempotent"])
        return sealed

    @staticmethod
    def _release_pin(lesson: dict) -> dict:
        scenario = lesson["scenario_refs"][0]
        return {
            "release_id": lesson["release_id"],
            "release_no": lesson["release_no"],
            "release_checksum": lesson["release_checksum"],
            "course_id": lesson["course_id"],
            "lesson_id": lesson["id"],
            "course_content_version": lesson["content_version"],
            "course_checksum": lesson["content_checksum"],
            "scenario_version": scenario["scenario_version"],
            "scenario_checksum": scenario["checksum"],
        }

    def _response_json(self, response) -> dict:
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()


if __name__ == "__main__":
    unittest.main()
