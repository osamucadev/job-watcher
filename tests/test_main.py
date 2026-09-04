from __future__ import annotations

import unittest

from app.main import safe_return_path


class ReturnPathTests(unittest.TestCase):
    def test_accepts_local_path(self) -> None:
        self.assertEqual(safe_return_path("/jobs", "/"), "/jobs")

    def test_rejects_external_and_protocol_relative_paths(self) -> None:
        self.assertEqual(safe_return_path("https://example.test", "/"), "/")
        self.assertEqual(safe_return_path("//example.test", "/"), "/")


if __name__ == "__main__":
    unittest.main()
