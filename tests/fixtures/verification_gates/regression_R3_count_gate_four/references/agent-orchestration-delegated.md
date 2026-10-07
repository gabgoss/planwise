# Agent Orchestration — Delegated Sessions

## 1.14 Spawn Prompt Composition

The spawn prompt names the task file, the session id, and the output directory.

## 1.15 Recovery Handling

Sequential dispatch writes Recovery incrementally; parallel dispatch returns a
status block instead.

## 1.16 Language Server Protocol Notes

The LSP section was folded into this subsection. See 1.16 for the folded content
and its rationale.

Callers that previously cited the standalone LSP section should now cite 1.16.

## 1.17 Status-Block Return Contract

The status block is bounded so it does not accumulate in the orchestrator window.

## Index

- 1.14 Spawn Prompt Composition
- 1.15 Recovery Handling
- 1.16 Language Server Protocol Notes
- 1.17 Status-Block Return Contract
