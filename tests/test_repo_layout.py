from __future__ import annotations

import importlib
import unittest


class RepoLayoutTests(unittest.TestCase):
    def test_package_runner_exports_helpers(self) -> None:
        runner = importlib.import_module("paperfeeder.pipeline.runner")
        self.assertTrue(callable(runner.main))
        self.assertTrue(callable(runner.run_pipeline))
        self.assertTrue(callable(runner._extract_report_urls))

    def test_feedback_cli_imports(self) -> None:
        feedback = importlib.import_module("paperfeeder.cli.apply_feedback")
        self.assertTrue(callable(feedback.main))


if __name__ == "__main__":
    unittest.main()
