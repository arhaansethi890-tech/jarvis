import ast
from pathlib import Path
import unittest

import safeguards


class SafeguardPolicyTests(unittest.TestCase):
    def test_brain_authorize_calls_are_classified(self):
        source = Path(__file__).with_name("brain.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        used_actions = set()

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Name) or node.func.id != "authorize":
                continue
            if node.args and isinstance(node.args[0], ast.Constant):
                if isinstance(node.args[0].value, str):
                    used_actions.add(node.args[0].value)

        configured_actions = (
            safeguards.ALWAYS_ALLOWED
            | safeguards.REQUIRES_APPROVAL
            | safeguards.ALWAYS_BLOCKED
        )
        self.assertLessEqual(used_actions, configured_actions)

    def test_action_categories_do_not_overlap(self):
        groups = (
            safeguards.ALWAYS_ALLOWED,
            safeguards.REQUIRES_APPROVAL,
            safeguards.ALWAYS_BLOCKED,
        )
        for index, group in enumerate(groups):
            for other in groups[index + 1:]:
                self.assertTrue(group.isdisjoint(other))

    def test_project_file_is_inside_read_boundary(self):
        allowed, _ = safeguards.check_read_path(__file__)
        self.assertTrue(allowed)

    def test_output_path_is_inside_write_boundary(self):
        output_file = Path(__file__).with_name("output") / "test-result.txt"
        allowed, _ = safeguards.check_write_path(output_file)
        self.assertTrue(allowed)


if __name__ == "__main__":
    unittest.main()
