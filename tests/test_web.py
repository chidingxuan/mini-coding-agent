"""网页接线测试：使用真实ASGI应用，不替换模型，不发送付费请求。"""

import unittest

from fastapi.testclient import TestClient

from backend.api import app
from backend import api


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

    def test_whitespace_question_does_not_save_history(self):
        response = self.client.post("/chat", json={"conversation_id": "blank-test", "question": "  \n "})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"]["code"], "invalid_input")
        self.assertEqual(api.load_history("blank-test"), [])

    def test_missing_configuration_does_not_call_model_or_save_history(self):
        previous_key = api.api_key
        try:
            api.api_key = None
            response = self.client.post("/chat", json={"conversation_id": "config-test", "question": "你好"})
        finally:
            api.api_key = previous_key
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"]["code"], "configuration_error")
        self.assertEqual(api.load_history("config-test"), [])


if __name__ == "__main__":
    unittest.main()
