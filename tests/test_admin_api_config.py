from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import SecretStr

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/api"))
from settings import settings  # noqa: E402
from services.operations import api_config  # noqa: E402


class AdminApiConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        fields = ("llm_provider", "deepseek_api_key", "deepseek_base_url", "deepseek_model",
                  "deepseek_model_pro", "deepseek_thinking", "github_publication_enabled",
                  "github_publication_token", "content_history_target_path")
        self.original = {field: getattr(settings, field) for field in fields}
        self.warning = api_config._configuration_warning
        settings.llm_provider = "mock"
        settings.deepseek_api_key = SecretStr("unit-test-key")
        settings.github_publication_enabled = True
        settings.github_publication_token = SecretStr("unit-test-token")
        settings.content_history_target_path = "infra/content-history-target.json"
        self.stored = {}
        self.save_patch = patch.object(api_config.persistence, "kv_set", side_effect=lambda ns, key, value: self.stored.update(value))
        self.save_patch.start()

    def tearDown(self) -> None:
        self.save_patch.stop()
        for field, value in self.original.items():
            setattr(settings, field, value)
        api_config._configuration_warning = self.warning

    def payload(self, **changes):
        return api_config.ApiConfigUpdate(**{
            "provider": "mock", "base_url": "https://api.deepseek.com", "model": "test-fast",
            "model_pro": "test-pro", "thinking": "disabled", **changes,
        })

    def test_legacy_ai_update_preserves_github_and_does_not_echo_keys(self) -> None:
        view = api_config.apply_api_config(self.payload())
        self.assertTrue(view.github_publication_enabled)
        self.assertEqual(self.stored["github_token"], "unit-test-token")
        self.assertEqual(view.github_repository, "falling-feather/Chronovita-Course-Content")
        self.assertNotIn("unit-test-key", view.model_dump_json())
        self.assertNotIn("unit-test-token", view.model_dump_json())

    def test_clearing_secrets_disables_their_services(self) -> None:
        view = api_config.apply_api_config(self.payload(provider="deepseek", clear_api_key=True, clear_github_token=True))
        self.assertEqual(view.provider, "mock")
        self.assertFalse(view.api_key_configured)
        self.assertFalse(view.github_publication_enabled)
        self.assertFalse(view.github_token_configured)

    def test_incomplete_or_untrusted_online_config_does_not_write(self) -> None:
        settings.deepseek_api_key = SecretStr("")
        for changes in ({"provider": "deepseek"}, {"provider": "deepseek", "api_key": "unit-test-key", "base_url": "https://untrusted.invalid"}):
            with self.assertRaises(ValueError):
                api_config.apply_api_config(self.payload(**changes))
        self.assertEqual(self.stored, {})

    def test_invalid_persisted_config_has_visible_safe_state(self) -> None:
        with patch.object(api_config.persistence, "kv_get", return_value={"provider": "bad"}):
            api_config.load_api_config()
        view = api_config._view()
        self.assertEqual(view.provider, "mock")
        self.assertFalse(view.github_publication_enabled)
        self.assertTrue(view.configuration_warning)

    def test_missing_binding_refuses_publication_before_persisting(self) -> None:
        settings.content_history_target_path = "infra/nonexistent-binding.json"
        with self.assertRaises(ValueError):
            api_config.apply_api_config(self.payload(github_publication_enabled=True))
        self.assertEqual(self.stored, {})
        self.assertTrue(api_config._view().github_configuration_error)


if __name__ == "__main__":
    unittest.main()
