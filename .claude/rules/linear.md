# Linear issue creation checklist

When creating an issue via `mcp__linear__save_issue`, always provide these fields:

1. **Labels** — at least one area label + type label if applicable
   - Area: `Pipeline`, `Reader`, `DevOps`, `QA`, `Testing`, `Config`
   - Type: `Bug`, `Feature`, `Improvement`, `Refactor`, `Regression`
2. **Parent** — set `parentId` when the issue belongs to an existing epic
3. **Milestone** — assign if one fits the scope; query milestones first if unsure
4. **Project** — `ATE2` for current active work, `ATE1` for legacy/infra
5. **Priority** — always set explicitly: 1=Urgent, 2=High, 3=Normal, 4=Low
