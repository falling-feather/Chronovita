import tempfile
import unittest
from pathlib import Path

from services import content


class ContentPathTests(unittest.TestCase):
    def test_configured_root_normalizes_aliases_before_release_path_comparison(self):
        original = content.content_root()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'alias').mkdir()
            supplied = root / 'alias' / '..' / 'content'
            try:
                content.configure(supplied)
                self.assertEqual(content.content_root(), supplied.resolve())
                self.assertEqual(content.sealed_dir(), supplied.resolve() / 'sealed')
            finally:
                content.configure(original)
