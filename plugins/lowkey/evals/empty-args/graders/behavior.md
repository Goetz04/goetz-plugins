---
type: llm
---
PASS if the final reply asks the user for an issue number or a task description and does not start work on a task. Mentions of options such as --keep or --resume are fine. Remarks about tool or sandbox errors during the git check are fine and do not count against the reply.
FAIL if the reply starts planning, invents a task or claims to have changed files.
