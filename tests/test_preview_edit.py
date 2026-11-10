"""使用临时真实文件验证修改预览，不替换模型、不调用付费API。"""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend import tool
from backend.errors import AgentError


class PreviewEditTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory(prefix="mini-agent-preview-test-")
        self.addCleanup(directory.cleanup)
        self.project_dir = Path(directory.name).resolve()
        previous_dir = tool.PROJECT_DIR
        tool.PROJECT_DIR = self.project_dir
        self.addCleanup(setattr, tool, "PROJECT_DIR", previous_dir)
        self.target = self.project_dir / "main.py"
        self.target.write_text('title = "海边"\nvalue = 1\n', encoding="utf-8")

    def test_diff_and_original_bytes(self):
        before = self.target.read_bytes()
        diff = tool.preview_edit("main.py", "value = 1", "value = 2")
        self.assertTrue(diff.startswith("--- a/main.py\n+++ b/main.py\n@@"))
        self.assertIn("-value = 1\n+value = 2\n", diff)
        self.assertIn('title = "海边"', diff)
        self.assertEqual(self.target.read_bytes(), before)

    def test_dispatch_returns_diff_string(self):
        arguments = {"path": "main.py", "old_text": "value = 1", "new_text": "value = 2"}
        before = self.target.read_bytes()
        diff = tool.execute_tool("preview_edit", json.dumps(arguments))
        self.assertIsInstance(diff, str)
        self.assertEqual(diff, tool.preview_edit(**arguments))
        self.assertEqual(self.target.read_bytes(), before)

    def test_tool_schema(self):
        names = [entry["function"]["name"] for entry in tool.TOOLS]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(names.count("preview_edit"), 1)
        schema = next(entry["function"]["parameters"] for entry in tool.TOOLS
                      if entry["function"]["name"] == "preview_edit")
        self.assertEqual(set(schema["required"]), {"path", "old_text", "new_text"})
        self.assertEqual(schema["properties"]["path"]["enum"], sorted(tool.READABLE_FILES))
        self.assertFalse(schema["additionalProperties"])

    def test_missing_extra_or_wrong_type_arguments(self):
        valid = {"path": "main.py", "old_text": "value = 1", "new_text": "value = 2"}
        cases = [
            {}, {"path": "main.py"}, {**valid, "extra": 1},
            {**valid, "old_text": None}, {**valid, "old_text": ""},
            {**valid, "new_text": None}, {**valid, "path": 1},
        ]
        before = self.target.read_bytes()
        for arguments in cases:
            with self.subTest(keys=list(arguments)):
                with self.assertRaises(AgentError) as caught:
                    tool.execute_tool("preview_edit", json.dumps(arguments))
                self.assertEqual(caught.exception.code, "invalid_tool_arguments")
                self.assertEqual(self.target.read_bytes(), before)

    def test_missing_repeated_or_overlapping_original_is_rejected(self):
        cases = [
            ("value = 1\n", "stale original"),
            ("target\ntarget\n", "target"),
            ("aaaa\n", "aaa"),
        ]
        for source, old_text in cases:
            with self.subTest(source=source):
                self.target.write_text(source, encoding="utf-8")
                before = self.target.read_bytes()
                with self.assertRaises(AgentError) as caught:
                    tool.preview_edit("main.py", old_text, "replacement")
                self.assertEqual(caught.exception.code, "invalid_tool_arguments")
                self.assertEqual(self.target.read_bytes(), before)

    def test_no_change_is_rejected(self):
        with self.assertRaises(AgentError) as caught:
            tool.preview_edit("main.py", "value = 1", "value = 1")
        self.assertEqual(caught.exception.code, "invalid_tool_arguments")

    def test_empty_replacement_previews_deletion(self):
        before = self.target.read_bytes()
        diff = tool.preview_edit("main.py", "value = 1\n", "")
        self.assertIn("-value = 1\n", diff)
        self.assertEqual(self.target.read_bytes(), before)

    def test_indentation_is_not_stripped(self):
        self.target.write_text("def example():\n    return 1\n", encoding="utf-8")
        diff = tool.preview_edit("main.py", "    return 1", "    return 2")
        self.assertIn("-    return 1\n+    return 2\n", diff)

    def test_missing_final_newline_is_marked_without_joining_lines(self):
        self.target.write_bytes(b"value = 1")
        diff = tool.preview_edit("main.py", "value = 1", "value = 2")
        self.assertIn("-value = 1\n\\ No newline at end of file\n+value = 2\n", diff)
        self.assertEqual(diff.count("\\ No newline at end of file"), 2)
        self.assertEqual(self.target.read_bytes(), b"value = 1")

    def test_final_newline_only_changes_are_visible(self):
        for before, after in (("value = 1", "value = 1\n"), ("value = 1\n", "value = 1")):
            with self.subTest(before=repr(before)):
                self.target.write_text(before, encoding="utf-8")
                diff = tool.preview_edit("main.py", before, after)
                self.assertIn("-value = 1", diff)
                self.assertIn("+value = 1", diff)
                self.assertEqual(diff.count("\\ No newline at end of file"), 1)
                self.assertEqual(self.target.read_text(encoding="utf-8"), before)

    def test_private_and_outside_paths_remain_rejected(self):
        private = self.project_dir / ".env"
        private.write_text("PRIVATE_TEST_MARKER", encoding="utf-8")
        before = self.target.read_bytes()
        for path in (".env", "../main.py", "/etc/passwd", "backend/storage.py"):
            with self.subTest(path=path):
                with self.assertRaises(AgentError) as caught:
                    tool.preview_edit(path, "value = 1", "value = 2")
                self.assertEqual(caught.exception.code, "tool_rejected")
                self.assertEqual(self.target.read_bytes(), before)
        self.assertEqual(private.read_text(encoding="utf-8"), "PRIVATE_TEST_MARKER")

    def test_text_and_resulting_file_limits(self):
        before = self.target.read_bytes()
        for old_text, new_text in (("x" * 20001, "x"), ("value = 1", "x" * 20001),
                                   ("value = 1", "界" * 7000)):
            with self.subTest(old_length=len(old_text), new_length=len(new_text)):
                with self.assertRaises(AgentError) as caught:
                    tool.preview_edit("main.py", old_text, new_text)
                self.assertEqual(caught.exception.code, "tool_rejected")
                self.assertEqual(self.target.read_bytes(), before)

    def test_symlink_cannot_expand_readable_files(self):
        private = self.project_dir / "private.py"
        private.write_text("value = 1\n", encoding="utf-8")
        directory = self.project_dir / "backend"
        directory.mkdir()
        (directory / "api.py").symlink_to(private)
        with self.assertRaises(AgentError) as caught:
            tool.preview_edit("backend/api.py", "value = 1", "value = 2")
        self.assertEqual(caught.exception.code, "tool_rejected")
        self.assertEqual(private.read_text(encoding="utf-8"), "value = 1\n")

    def test_unencodable_replacement_is_rejected(self):
        with self.assertRaises(AgentError) as caught:
            tool.preview_edit("main.py", "value = 1", "\ud800")
        self.assertEqual(caught.exception.code, "invalid_tool_arguments")

    def test_replacement_code_is_never_executed(self):
        marker = self.project_dir / "must-not-be-created.txt"
        replacement = f"__import__('pathlib').Path({str(marker)!r}).write_text('executed')"
        before = self.target.read_bytes()
        diff = tool.preview_edit("main.py", "value = 1", replacement)
        self.assertIn("+" + replacement, diff)
        self.assertFalse(marker.exists())
        self.assertEqual(self.target.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
