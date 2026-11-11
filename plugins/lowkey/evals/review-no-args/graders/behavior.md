---
type: llm
---
PASS if the reply identifies the review target as the branch feature against its merge-base with main, names the changed file src/price.py or the commit that adds the discount check, proposes test commands and asks the user to confirm them before anything runs.
FAIL if the reply changes files, starts reviewers before the confirmation, reviews uncommitted changes, invents a diff or claims findings.
