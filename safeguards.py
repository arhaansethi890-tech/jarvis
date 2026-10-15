
"""
JARVIS SAFEGUARDS
Central policy for actions JARVIS may perform.

Important:
This module must be called by brain.py before an action happens.
It does not independently sandbox Python or Windows.
"""

from pathlib import Path
from enum import Enum
import os


# ---------- CONFIGURATION ----------

PROJECT_DIR = Path(__file__).resolve().parent

# JARVIS may read files only inside these directories
# when code explicitly uses the file-access checks below.
READABLE_DIRS = [
    PROJECT_DIR,
]

# These folders may be used for new, non-sensitive output files.
WRITABLE_DIRS = [
    PROJECT_DIR / "output",
]

# These actions are permitted without asking each time.
ALWAYS_ALLOWED = {
    "answer_question",
    "tell_time",
    "tell_date",
    "calculate",
    "open_approved_app",
     "open_approved_folder",
    "open_approved_website",
    "search_web",
    "search_youtube",
}

# These actions require explicit approval from the user.
REQUIRES_APPROVAL = {
    "read_file",
    "create_file",
    "modify_file",
    "modify_own_code",
    "send_message",
    "download_file",
}

# These actions are blocked regardless of AI suggestions.
ALWAYS_BLOCKED = {
    "delete_file",
    "execute_arbitrary_command",
    "install_software",
    "change_security_settings",
    "disable_security_software",
    "access_passwords",
    "access_browser_cookies",
    "modify_safeguards",
    "grant_self_permissions",
    "run_unknown_program",
}


class Decision(Enum):
    ALLOW = "allow"
    APPROVAL_REQUIRED = "approval_required"
    BLOCK = "block"


def _inside_directory(path, allowed_dirs):
    """Return True only when the resolved path is inside an allowed folder."""
    try:
        resolved = Path(path).resolve()

        for directory in allowed_dirs:
            root = Path(directory).resolve()

            try:
                resolved.relative_to(root)
                return True
            except ValueError:
                continue

    except (OSError, RuntimeError, ValueError):
        return False

    return False


def check_read_path(path):
    """Check whether a requested file is inside an approved read folder."""
    if not _inside_directory(path, READABLE_DIRS):
        return False, "This file is outside JARVIS's approved read folders."

    if not Path(path).is_file():
        return False, "The requested file does not exist or is not a file."

    return True, "Read path is within an approved folder."


def check_write_path(path):
    """Check whether a new or modified file is in an approved output folder."""
    if not _inside_directory(path, WRITABLE_DIRS):
        return False, "Writes are restricted to the approved output folder."

    return True, "Write path is within an approved folder."


def authorize(action, target=None, approved=False):
    """
    Return (Decision, explanation).

    'approved=True' must come from a real user approval interface,
    never from the AI model or its generated text.
    """
    action = str(action).strip().lower()

    if action in ALWAYS_BLOCKED:
        return Decision.BLOCK, f"Blocked by security policy: {action}"

    if action in ALWAYS_ALLOWED:
        return Decision.ALLOW, f"Allowed by policy: {action}"

    if action == "read_file":
        if not target:
            return Decision.BLOCK, "A file path is required."

        allowed, reason = check_read_path(target)
        if not allowed:
            return Decision.BLOCK, reason

    elif action in {"create_file", "modify_file"}:
        if not target:
            return Decision.BLOCK, "A file path is required."

        allowed, reason = check_write_path(target)
        if not allowed:
            return Decision.BLOCK, reason

    elif action == "modify_own_code":
        # Code changes are never automatically authorized.
        if not approved:
            return (
                Decision.APPROVAL_REQUIRED,
                "JARVIS code changes require your explicit approval."
            )

        return (
            Decision.BLOCK,
            "Direct self-modification is disabled. "
            "Use a reviewed patch workflow instead."
        )

    elif action in REQUIRES_APPROVAL:
        if not approved:
            return (
                Decision.APPROVAL_REQUIRED,
                f"Your approval is required for: {action}"
            )

        return (
            Decision.BLOCK,
            "This action is not implemented as a safe operation yet."
        )

    else:
        # Unknown actions must never be allowed by default.
        return (
            Decision.BLOCK,
            f"Unknown action blocked by default: {action}"
        )

    if action in REQUIRES_APPROVAL and not approved:
        return (
            Decision.APPROVAL_REQUIRED,
            f"Your approval is required for: {action}"
        )

    return Decision.ALLOW, f"Allowed by policy: {action}"


def get_security_summary():
    """Return a readable summary for the GUI or help command."""
    return {
        "project_directory": str(PROJECT_DIR),
        "readable_directories": [
            str(path) for path in READABLE_DIRS
        ],
        "writable_directories": [
            str(path) for path in WRITABLE_DIRS
        ],
        "approval_required": sorted(REQUIRES_APPROVAL),
        "blocked_actions": sorted(ALWAYS_BLOCKED),
    }
