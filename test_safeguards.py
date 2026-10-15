
from safeguards import authorize, Decision, get_security_summary

tests = [
    ("answer_question", None, False),
    ("execute_arbitrary_command", None, False),
    ("modify_own_code", None, False),
    ("grant_self_permissions", None, True),
    ("unknown_action", None, True),
]

for action, target, approved in tests:
    decision, reason = authorize(action, target, approved)
    print(f"{action}: {decision.value} — {reason}")

print("\nSecurity configuration:")
for key, value in get_security_summary().items():
    print(f"{key}: {value}")
