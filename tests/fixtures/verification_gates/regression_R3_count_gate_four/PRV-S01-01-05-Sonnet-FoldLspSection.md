# Task: FoldLspSection

**Task ID:** PRV-S01-01-05
**Agent:** Sonnet
**Output:** `references/agent-orchestration-delegated.md`

---

## Objective

Fold the standalone LSP section into the delegated-orchestration reference.

---

## Execution Steps

1. Open `references/agent-orchestration-delegated.md`.
2. Fold the LSP content into the numbered subsection and repoint its callers.

---

## Verification Commands

> [!verify] Before / After Commands
> **Before:** *(runner)*
> ```bash
> wc -l references/agent-orchestration-delegated.md
> ```
> **After:** *(runner)*
> ```bash
> grep -c '1.16' references/agent-orchestration-delegated.md   # expect ≥1 (LSP section folded)
> ```

---

## Success Criteria

- [ ] The LSP content is folded into the numbered subsection
