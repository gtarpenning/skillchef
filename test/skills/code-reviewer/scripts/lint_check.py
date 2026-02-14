"""Example supporting script for the code-reviewer skill."""


def check_diff(diff_text: str) -> list[str]:
    issues = []
    for i, line in enumerate(diff_text.splitlines(), 1):
        if line.startswith("+") and "TODO" in line:
            issues.append(f"Line {i}: New TODO found — consider resolving before merge")
    return issues
