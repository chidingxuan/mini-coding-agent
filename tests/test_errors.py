"""错误映射和真实工具的本地检查；不替换模型业务，不发送API请求。"""

import json
import unittest

import httpx
from openai import (
    APIConnectionError, APIStatusError, APITimeoutError,
    AuthenticationError, OpenAIError, PermissionDeniedError, RateLimitError,
)

from backend.errors import AgentError, model_request_error
from backend.tool import execute_tool


class ErrorTests(unittest.TestCase):
    def test_sdk_errors_are_safe(self):
        request = httpx.Request("POST", "https://api.deepseek.com/chat/completions")
        private_marker = "DO_NOT_EXPOSE_REQUEST_OR_KEY"

        def status_error(cls, status):
            return cls(private_marker, response=httpx.Response(status, request=request), body=None)

        cases = [
            (APITimeoutError(request=request), "model_timeout", 504),
            (APIConnectionError(message=private_marker, request=request), "model_connection_failed", 503),
            (status_error(AuthenticationError, 401), "model_auth_failed", 503),
            (status_error(PermissionDeniedError, 403), "model_permission_denied", 503),
            (status_error(RateLimitError, 429), "model_rate_limited", 429),
            (status_error(APIStatusError, 402), "model_balance_exhausted", 503),
            (status_error(APIStatusError, 500), "model_service_error", 502),
            (status_error(APIStatusError, 503), "model_service_error", 502),
            (status_error(APIStatusError, 400), "model_request_rejected", 502),
            (OpenAIError(private_marker), "model_request_failed", 502),
        ]
        for error, code, status in cases:
            with self.subTest(code=code, status=status):
                safe = model_request_error(error)
                self.assertIsInstance(safe, ValueError)
                self.assertEqual(safe.code, code)
                self.assertEqual(safe.status_code, status)
                self.assertNotIn(private_marker, str(safe))

    def test_tool_rejection_codes(self):
        cases = [
            ("shell", "{}", "tool_rejected"),
            ("read_file", '{"path":".env"}', "tool_rejected"),
            ("read_file", '{"path":"../main.py"}', "tool_rejected"),
            ("read_file", '{"path":"/etc/passwd"}', "tool_rejected"),
            ("read_file", "not JSON", "invalid_tool_arguments"),
            ("read_file", "[]", "invalid_tool_arguments"),
            ("read_file", "{}", "invalid_tool_arguments"),
            ("read_file", '{"path":1}', "invalid_tool_arguments"),
            ("read_file", '{"path":"main.py","extra":1}', "invalid_tool_arguments"),
            ("list_files", '{"path":"main.py"}', "invalid_tool_arguments"),
        ]
        for name, arguments, code in cases:
            with self.subTest(name=name, arguments=arguments):
                with self.assertRaises(AgentError) as caught:
                    execute_tool(name, arguments)
                self.assertEqual(caught.exception.code, code)

    def test_real_tools_still_work(self):
        files = json.loads(execute_tool("list_files", "{}"))
        self.assertEqual(files, ["backend/api.py", "backend/llm.py", "main.py", "workspace/demo.py"])
        self.assertIn("ask_agent", execute_tool("read_file", '{"path":"main.py"}'))


if __name__ == "__main__":
    unittest.main()
