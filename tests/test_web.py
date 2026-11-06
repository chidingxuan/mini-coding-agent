"""网页接线测试：使用真实ASGI应用，不替换模型，不发送付费请求。"""

import unittest

from fastapi.testclient import TestClient

from backend.api import app


class WebTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()

    def test_home(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("Mini Code Agent", response.text)
        self.assertIn('/assets/app.js', response.text)
        self.assertIn('/assets/app.css', response.text)

    def test_assets(self):
        for filename in ("app.js", "app.css"):
            with self.subTest(filename=filename):
                response = self.client.get(f"/assets/{filename}")
                self.assertEqual(response.status_code, 200)

    def test_private_files_not_served(self):
        for path in (
            "/.env", "/.git/config", "/main.py", "/backend/api.py",
            "/assets/.env", "/assets/%2e%2e/%2e%2e/%2e%2e/.env",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)

    def test_existing_docs_and_validation(self):
        self.assertEqual(self.client.get("/docs").status_code, 200)
        self.assertEqual(self.client.post("/chat", json={"conversation_id": "web-test"}).status_code, 422)
        self.assertEqual(self.client.post("/chat", json={"conversation_id": "web-test", "question": ""}).status_code, 422)


if __name__ == "__main__":
    unittest.main()
