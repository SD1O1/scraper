import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class ProjectShapeTests(unittest.TestCase):
    def test_frontend_exposes_reddit_target_workflow(self):
        page = (ROOT / "index.html").read_text(encoding="utf-8")
        for control in ("Subreddit(s)", "Include keywords", "Exclude keywords", "Export CSV"):
            self.assertIn(control, page)

    def test_backend_has_storage_and_reddit_collection_routes(self):
        backend = (ROOT / "backend.py").read_text(encoding="utf-8")
        for route in ('@app.post("/api/fetch")', 'CREATE TABLE IF NOT EXISTS targets', 'INSERT OR IGNORE INTO posts'):
            self.assertIn(route, backend)


if __name__ == "__main__":
    unittest.main()
