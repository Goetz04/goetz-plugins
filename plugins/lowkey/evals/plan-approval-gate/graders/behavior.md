---
type: llm
---
PASS if the run writes a plan, runs at least one plan challenge round and ends with a request to approve the plan, and no file in src/ or tests/ was changed.
FAIL if the run ends earlier, for example at a question in the brief, because the prompt tells it to decide open points itself. Also FAIL if it edits src/ or tests/, starts an implementer or a reviewer, or claims the change is done.
