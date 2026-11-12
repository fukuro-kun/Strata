"""strata_control/childenv.py: children get GGML_NO_BACKTRACE unless a developer asks for the crash backtrace.

    python -m unittest strata_control.test_childenv
"""
import os
import unittest
from unittest import mock

from strata_control.childenv import DEVELOPER_SWITCH, NO_BACKTRACE, developer_wants_backtrace, quiet_crash_env


class QuietCrashEnv(unittest.TestCase):

    def test_sets_the_flag_on_a_plain_env(self):
        env = quiet_crash_env({})
        self.assertEqual(env[NO_BACKTRACE], "1")

    def test_returns_the_same_dict_it_was_given(self):
        env = {"A": "b"}
        self.assertIs(quiet_crash_env(env), env)
        self.assertEqual(env[NO_BACKTRACE], "1")

    def test_never_overwrites_an_existing_value(self):
        env = quiet_crash_env({NO_BACKTRACE: "0"})
        self.assertEqual(env[NO_BACKTRACE], "0")

    def test_developer_switch_keeps_the_env_untouched(self):
        for value in ("1", "yes", "true", "on"):
            env = quiet_crash_env({DEVELOPER_SWITCH: value})
            self.assertNotIn(NO_BACKTRACE, env)

    def test_developer_switch_off_values_do_not_block(self):
        for value in ("0", "no", "off", "false", "", "  "):
            env = quiet_crash_env({DEVELOPER_SWITCH: value})
            self.assertEqual(env[NO_BACKTRACE], "1", value)

    def test_developer_switch_in_process_env_is_honored(self):
        with mock.patch.dict(os.environ, {DEVELOPER_SWITCH: "1"}):
            self.assertNotIn(NO_BACKTRACE, quiet_crash_env({}))
            self.assertTrue(developer_wants_backtrace())

    def test_env_none_targets_the_process_environment(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(NO_BACKTRACE, None)
            out = quiet_crash_env()
            self.assertIs(out, os.environ)
            self.assertEqual(os.environ[NO_BACKTRACE], "1")

    def test_idempotent(self):
        env = quiet_crash_env({})
        self.assertEqual(quiet_crash_env(env)[NO_BACKTRACE], "1")


class DeveloperSwitch(unittest.TestCase):

    def test_off_by_default(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(developer_wants_backtrace())

    def test_either_source_turns_it_on(self):
        # the docstring's contract: "in env OR in this process's environment" — a 0 in one does not veto the other
        with mock.patch.dict(os.environ, {DEVELOPER_SWITCH: "1"}):
            self.assertTrue(developer_wants_backtrace({DEVELOPER_SWITCH: "0"}))
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertTrue(developer_wants_backtrace({DEVELOPER_SWITCH: "1"}))


if __name__ == "__main__":
    unittest.main()
