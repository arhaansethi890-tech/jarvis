import unittest

from safeguards import authorize, Decision
from brain import JarvisBrain


class AuthorizationTests(unittest.TestCase):
    def test_allowed_actions_are_allowed(self):
        cases = (
            ("answer_question", None),
            ("open_approved_app", "calculator"),
        )
        for action, target in cases:
            with self.subTest(action=action):
                decision, _ = authorize(action, target=target)
                self.assertEqual(decision, Decision.ALLOW)

    def test_blocked_actions_are_blocked(self):
        actions = (
            "execute_arbitrary_command",
            "run_unknown_program",
            "modify_safeguards",
            "grant_self_permissions",
        )
        for action in actions:
            with self.subTest(action=action):
                decision, _ = authorize(action)
                self.assertEqual(decision, Decision.BLOCK)

    def test_sensitive_actions_require_approval(self):
        decision, _ = authorize("modify_own_code")
        self.assertEqual(decision, Decision.APPROVAL_REQUIRED)

    def test_unknown_actions_are_blocked(self):
        decision, _ = authorize("unknown_action")
        self.assertEqual(decision, Decision.BLOCK)

    def test_exit_command_stops_the_brain(self):
        brain = JarvisBrain(warm_up=False)
        response = brain.respond("exit")
        self.assertEqual(response, "Until next time, sir.")
        self.assertFalse(brain.running)


if __name__ == "__main__":
    unittest.main()
