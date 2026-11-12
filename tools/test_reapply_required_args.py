#!/usr/bin/env python3
"""Tests for tools/offline/reapply_required_args.py — pure apply_required
logic plus spec validation. No GPU, no downloads:
    python3 tools/test_reapply_required_args.py
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "offline"))
import reapply_required_args as r  # noqa: E402


def run(args, required, forbidden=()):
    return r.apply_required(args, required, list(forbidden))


class TestRequired(unittest.TestCase):
    def test_conform(self):
        args = ["--pack", "p", "--max-context", "262144", "--vision"]
        new, ch = run(args, {"--max-context": "262144", "--vision": None})
        self.assertEqual(new, args)
        self.assertEqual(ch, [])

    def test_value_fixed(self):
        new, ch = run(["--max-context", "65536"], {"--max-context": "262144"})
        self.assertEqual(new, ["--max-context", "262144"])
        self.assertIn("65536 -> 262144", ch[0])

    def test_missing_key_appended(self):
        new, _ = run(["--kv", "int8"], {"--resident-budget-gib": "12"})
        self.assertEqual(new, ["--kv", "int8", "--resident-budget-gib", "12"])

    def test_bare_value_flag_gets_value(self):
        new, ch = run(["--max-context", "--kv", "int8"], {"--max-context": "262144"})
        self.assertEqual(new, ["--max-context", "262144", "--kv", "int8"])

    def test_flag_at_end_gets_value(self):
        new, _ = run(["--kv", "int8", "--max-context"], {"--max-context": "262144"})
        self.assertEqual(new, ["--kv", "int8", "--max-context", "262144"])

    def test_missing_flag_added(self):
        new, _ = run(["--kv", "int8"], {"--vision": None})
        self.assertIn("--vision", new)

    def test_duplicate_keys_collapsed(self):
        # the engine takes the LAST occurrence — a stray second pair must go
        args = ["--max-context", "262144", "--kv", "int8", "--max-context", "65536"]
        new, ch = run(args, {"--max-context": "262144"})
        self.assertEqual(new, ["--max-context", "262144", "--kv", "int8"])
        self.assertTrue(any("duplicate" in c for c in ch))

    def test_duplicate_solo_flag_collapsed(self):
        new, ch = run(["--vision", "--kv", "int8", "--vision"], {"--vision": None})
        self.assertEqual(new.count("--vision"), 1)

    def test_missing_first_value_does_not_shift_duplicate_removal(self):
        args = ["--max-context", "--kv", "int8", "--max-context", "65536", "--vision"]
        new, _ = run(args, {"--max-context": "262144"})
        self.assertEqual(new, ["--max-context", "262144", "--kv", "int8", "--vision"])

    def test_bare_duplicate_preserves_the_following_flag(self):
        args = ["--max-context", "65536", "--kv", "int8", "--max-context", "--vision"]
        new, _ = run(args, {"--max-context": "262144"})
        self.assertEqual(new, ["--max-context", "262144", "--kv", "int8", "--vision"])

    def test_numeric_want_coerced(self):
        new, _ = run([], {"--max-context": 262144})
        self.assertEqual(new, ["--max-context", "262144"])

    def test_nonstring_args_coerced(self):
        new, _ = run(["--max-context", 65536], {"--max-context": "262144"})
        self.assertEqual(new, ["--max-context", "262144"])


class TestForbidden(unittest.TestCase):
    def test_flag_removed(self):
        new, _ = run(["--mmap-experts", "--kv", "int8"], {}, ["--mmap-experts"])
        self.assertNotIn("--mmap-experts", new)

    def test_flag_with_value_removed(self):
        new, ch = run(["--ple-io", "direct", "--kv", "int8"], {}, ["--ple-io"])
        self.assertEqual(new, ["--kv", "int8"])
        self.assertIn("--ple-io direct", ch[0])

    def test_flag_at_end(self):
        new, _ = run(["--kv", "int8", "--mmap-experts"], {}, ["--mmap-experts"])
        self.assertEqual(new, ["--kv", "int8"])

    def test_multi_occurrence(self):
        new, _ = run(["--x", "--a", "1", "--x"], {}, ["--x"])
        self.assertNotIn("--x", new)

    def test_single_dash_value_not_eaten(self):
        # "--ple-io -1": the token after the flag starts with '-' but not '--';
        # this tool treats it as the flag's value and drops both
        new, _ = run(["--ple-io", "-1", "--kv", "int8"], {}, ["--ple-io"])
        self.assertEqual(new, ["--kv", "int8"])


class TestInsertPosition(unittest.TestCase):
    def test_new_tokens_at_forbidden_gap(self):
        args = ["--kv", "int8", "--mmap-experts", "--vision"]
        new, _ = run(args, {"--resident-budget-gib": "12"}, ["--mmap-experts"])
        self.assertEqual(new, ["--kv", "int8", "--resident-budget-gib", "12", "--vision"])


class TestValidation(unittest.TestCase):
    def test_missing_config_name(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x-required-args.json"
            p.write_text('{"required": {}}')
            with self.assertRaises(SystemExit):
                r.load_required(p)

    def test_bad_key_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x-required-args.json"
            p.write_text('{"config_name": "c", "required": {"kv": "int8"}}')
            with self.assertRaises(SystemExit):
                r.load_required(p)

    def test_required_forbidden_overlap_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x-required-args.json"
            p.write_text('{"config_name": "c", "required": {"--a": null}, "forbidden": ["--a"]}')
            with self.assertRaises(SystemExit):
                r.load_required(p)

    def test_broken_json_fails(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x-required-args.json"
            p.write_text("{broken")
            with self.assertRaises(SystemExit):
                r.load_required(p)


if __name__ == "__main__":
    unittest.main(verbosity=2)
