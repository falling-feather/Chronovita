from pathlib import Path
import unittest

from scripts.check_project_docs import validate_project_docs


class ProjectDocumentationTests(unittest.TestCase):
    def test_canonical_documents_match_the_application_version(self):
        project_root = Path(__file__).resolve().parents[1]
        self.assertEqual(validate_project_docs(project_root), [])


if __name__ == "__main__":
    unittest.main()
