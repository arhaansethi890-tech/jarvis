
from safeguards import authorize, Decision

tests = [
    ("answer_question", None, Decision.ALLOW),
    ("open_approved_app", "calculator", Decision.ALLOW),
    ("execute_arbitrary_command", None, Decision.BLOCK),
    ("run_unknown_program", None, Decision.BLOCK),
    ("modify_safeguards", None, Decision.BLOCK),
    ("grant_self_permissions", None, Decision.BLOCK),
    ("modify_own_code", None, Decision.APPROVAL_REQUIRED),
]

for action, target, expected in tests:
    actual, reason = authorize(action, target=target)
    passed = actual == expected
    print(f"{'PASS' if passed else 'FAIL'} | {action}")
    if not passed:
        print(f"  Expected: {expected.value}")
        print(f"  Actual:   {actual.value}")
    print(f"  {reason}\n")
