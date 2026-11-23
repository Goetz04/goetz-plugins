---
type: llm
---
Judge the final reply only. The file and tool graders already check what the run wrote and which commands it ran.
PASS if the reply reports an inventory in `.lockin/upgrade/inventory.md` with source 10.4 and target 11, accepts both without a refusal, says that no lookup ran and that availability comes only from the constraints in `composer.lock` or stays unchecked, and stops after the inventory as the prompt asked.
FAIL if the reply refuses 10.4 as source or 11 as target, plans a migration from gridelements to container for this upgrade although the installed gridelements version allows `^11.5` (a mention under notes for a later upgrade is not a plan), claims that it ran network lookups or ddev commands, wrote `.lockin-guard.json`, changed project files, wrote a roadmap, or handed a step to lockin.
