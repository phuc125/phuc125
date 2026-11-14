"""
Integration tests for Program A (live_main.py) safety interlocks.
Verifies that `live_main.py --mode live` refuses execution when unauthorized,
and `live_main.py --mode monitor` runs cleanly in read-only mode.
"""
from __future__ import annotations

import tempfile
import os
import unittest

import live_main


class TestLiveProgramSafety(unittest.TestCase):
    def test_live_mode_refuses_without_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["DATABASE_PATH"] = f"{tmpdir}/live_test.db"
            os.environ["LIVE_TRADING_AUTHORIZED"] = "false"
            exit_code = live_main.main(["--mode", "live"])
            self.assertEqual(exit_code, 1)

    def test_monitor_mode_executes_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["DATABASE_PATH"] = f"{tmpdir}/monitor_test.db"
            exit_code = live_main.main(["--mode", "monitor"])
            self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()
