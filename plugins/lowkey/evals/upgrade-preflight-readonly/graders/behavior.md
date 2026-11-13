---
type: llm
---
Judge the final reply only. The file and tool graders already check what the run wrote and which commands it ran.
PASS if the reply reports an inventory in `.lockin/upgrade/inventory.md` with source 11.5, names gridelements as a blocker, says that extension availability stays unchecked because lookups were declined, and stops after the inventory as the prompt asked.
FAIL if the reply claims that it ran network lookups or ddev commands, wrote `.lockin-guard.json`, changed project files, wrote a roadmap, or handed a step to lockin.
