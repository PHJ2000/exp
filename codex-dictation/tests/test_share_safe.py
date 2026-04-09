from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from codex_share_safe import export_share_safe_file, mask_share_safe_text, sanitize_for_sharing  # noqa: E402


class ShareSafeTextTests(unittest.TestCase):
    def test_masks_home_path_and_local_host(self):
        text = r"Open C:\Users\ParkJaeHong\AppData\Local\CodexDictation\codex_dictation.log via http://127.0.0.1:11434"
        masked = mask_share_safe_text(text)
        self.assertIn("<user-home>/AppData/Local/CodexDictation/codex_dictation.log", masked)
        self.assertIn("http://<local-host>:11434", masked)
        self.assertNotIn("ParkJaeHong", masked)
        self.assertNotIn("127.0.0.1", masked)

    def test_prefers_project_relative_path(self):
        sample = PROJECT_DIR / "README.md"
        masked = mask_share_safe_text(str(sample), project_root=PROJECT_DIR.parent)
        self.assertEqual(masked, "codex-dictation/README.md")


class ShareSafeJsonTests(unittest.TestCase):
    def test_can_mask_text_fields_optionally(self):
        payload = {
            "url": "http://localhost:11434",
            "text": "비밀 문장입니다",
            "path": r"C:\Users\ParkJaeHong\secret.txt",
        }
        masked = sanitize_for_sharing(payload, mask_text_fields=True)
        self.assertEqual(masked["text"], "<masked-text:8 chars>")
        self.assertEqual(masked["url"], "http://<local-host>:11434")
        self.assertEqual(masked["path"], "<user-home>/secret.txt")

    def test_exports_plain_text_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_dir = Path(tmp_dir)
            source = temp_dir / "sample.log"
            output = temp_dir / "sample.share-safe.log"
            source.write_text(r"host=localhost path=C:\Users\ParkJaeHong\sample.txt", encoding="utf-8")
            export_share_safe_file(source, output)
            masked = output.read_text(encoding="utf-8")
            self.assertIn("host=<local-host>", masked)
            self.assertIn("path=<user-home>/sample.txt", masked)


if __name__ == "__main__":
    unittest.main()
