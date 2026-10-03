# 00001 - Lead deny messages with the exact recovery command

## Problem

In unattended sessions every hook denial costs a full model turn: the agent reads the deny, reasons, retries. The 2026-07-19 authoring audit found aegis deny texts explain policy well but do not always LEAD with the drop-in replacement, and one hook class (suppression markers) leaves the pre-existing-marker case to guesswork. v0.3.1 fixed the dead-tool wording; this PRD finishes the unattended ergonomics.

## Goal

One denial, one retry: the first line of every deny message is a copy-pasteable replacement for the exact command that was blocked, not a policy summary.

## Requirements

- R1: prefer_tools, block_poll_loops, block_devlocal_redirects, block_force_push deny messages restructure to: line 1 = concrete replacement built from the blocked command where feasible (e.g. blocked `grep -r foo src` → `rg -n "foo" src`), then the policy sentence. Where synthesis is not feasible, line 1 is the closest template.
- R2: block_suppression_markers: when the marker already exists in the file (agent is moving/reformatting, not adding), say so and allow; when newly added, the deny names the fix-it path (fix the finding, or surface it per rules/coding-style.md warnings policy).
- R3: gateguard deny text gains one closing line for unattended contexts: "Unattended: gather the facts from the file itself, present them, retry once; if still denied, skip and record the denial" - consistent with the buvis unattended contract.
- R4: Tests updated alongside each message change (the 227-test suite pins message shapes).

## Acceptance

- For a corpus of representative blocked commands (fixture list), the first line of each deny parses as a runnable command or an explicit template.
- Suppression-marker move/reformat fixture is allowed; newly-added fixture is denied with the fix-it path named.

## Out of scope

- New hooks; wording already shipped in v0.3.1.

## Notes

Evidence: buvis home dev/local/audit-results/2026-07-19-authoring-efficiency-audit.md (F4 omitted-edges, aegis).
