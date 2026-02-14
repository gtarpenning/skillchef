---
name: code-reviewer
description: Review code changes for quality, bugs, and style issues. Use when the user asks for a code review or submits a diff.
---

# Code Reviewer

Review code with a focus on correctness, readability, and maintainability.

## Process

1. Read the diff or code provided
2. Check for bugs, edge cases, and logic errors
3. Evaluate naming, structure, and style
4. Suggest improvements with brief rationale

## Output Format

For each finding:
- **File**: path
- **Line**: number
- **Severity**: error | warning | nit
- **Comment**: what to fix and why
