"""Tests for config schema helpers and feedback-related settings."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from paperfeeder.config.schema import Config, _parse_loose_bool
from paperfeeder.pipeline.runner import _feedback_email_attachment_paths


class ParseLooseBoolTests(unittest.TestCase):
    def test_yaml_string_false_disables(self) -> None:
        self.assertFalse(_parse_loose_bool("false", default=True))
        self.assertFalse(_parse_loose_bool("FALSE", default=True))
        self.assertFalse(_parse_loose_bool("0", default=True))
        self.assertFalse(_parse_loose_bool("no", default=True))
        self.assertFalse(_parse_loose_bool("off", default=True))

    def test_real_bool(self) -> None:
        self.assertTrue(_parse_loose_bool(True, default=False))
        self.assertFalse(_parse_loose_bool(False, default=True))

    def test_default_on_none_or_empty_string(self) -> None:
        self.assertTrue(_parse_loose_bool(None, default=True))
        self.assertFalse(_parse_loose_bool(None, default=False))
        self.assertTrue(_parse_loose_bool("", default=True))


class FeedbackWebViewerFromYamlTests(unittest.TestCase):
    def test_quoted_false_string_in_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "config.yaml"
            missing_user = Path(tmp) / "no_user_settings.yaml"
            cfg.write_text(
                f"user_settings_path: {missing_user.as_posix()}\n"
                "feedback_web_viewer_link_in_email: 'false'\n"
                "email_to: x@y.z\n",
                encoding="utf-8",
            )
            c = Config.from_yaml(str(cfg))
            self.assertFalse(c.feedback_web_viewer_link_in_email)


class FeedbackEmailAttachmentPathsTests(unittest.TestCase):
    def test_modes(self) -> None:
        m, q = "/a/manifest.json", "/a/template.json"
        self.assertEqual(_feedback_email_attachment_paths("all", m, q), [m, q])
        self.assertEqual(_feedback_email_attachment_paths("manifest", m, q), [m])
        self.assertEqual(_feedback_email_attachment_paths("none", m, q), [])


if __name__ == "__main__":
    unittest.main()
