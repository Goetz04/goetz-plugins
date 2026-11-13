---
type: llm
---
PASS if the run writes a roadmap with steps for the rung 12 to 13 and ends with a request to approve the roadmap.
FAIL if it ends earlier at a question the prompt already answered, prints a `/lowkey:lockin` command as the next action, marks a step as handed off, or starts a subagent.
