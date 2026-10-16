import hashlib
import re
import tomllib
import unittest
from scripts.configure_secret_scan import PORTRAIT_PATTERN, PORTRAIT_PATHS, build_config


class SecretScanPolicyTests(unittest.TestCase):
    def test_exceptions_are_exact_public_asset_fields_and_limited_paths(self):
        config = tomllib.loads(build_config('[allowlist]\npaths = []\n'))
        rule = config['allowlists'][-1]
        self.assertEqual(rule['condition'], 'AND')
        self.assertEqual(rule['targetRules'], ['generic-api-key'])
        self.assertEqual(rule['regexTarget'], 'match')
        public_id = 'L103-duke-xiao'
        self.assertIsNotNone(re.search(PORTRAIT_PATTERN, 'portrait_asset_key="' + public_id + '"'))
        self.assertIsNone(re.search(PORTRAIT_PATTERN, 'api_key="' + public_id + '"'))
        unknown = 'sk-' + hashlib.sha256(b'negative test, not a credential').hexdigest()
        self.assertIsNone(re.search(PORTRAIT_PATTERN, 'portrait_asset_key="' + unknown + '"'))
        self.assertFalse(any(re.search(pattern, 'apps/api/settings.py') for pattern in PORTRAIT_PATHS))

    def test_changed_upstream_shape_fails_closed(self):
        with self.assertRaises(ValueError):
            build_config('[[allowlists]]\npaths=[]\n')
