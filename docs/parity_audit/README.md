# Parity audit — completeness verification (VB NIT → Vaultkeeper)

**Goal:** guarantee that no functionality or experience in the original VB.NET
*NWN Installer Tool* was silently dropped by the Python port — evaluated at the
granularity of *each method, each event handler, each control*, not just each
menu command.

This exists because the earlier parity work (`../PARITY.md`, the dead-chrome
audit) is thorough at the **command level** (185 menu/ribbon/toolbar ids) and the
**screen level** (~26 dialogs), but three owner-spotted divergences —

1. empty mod groups not rendered for drag-drop,
2. ribbon tabs centered instead of left-aligned,
3. the Advanced Settings screen far shallower than the original —

all live *below* that: in event-handler **behavior**, Designer **layout
properties**, and dialog **control-set depth**. A command-existence check cannot
see them. This audit enumerates those finer layers.

## The idea: a machine-generated denominator

The set of "things the original does" is **derived mechanically from the VB
source**, so it cannot be under-counted by human oversight. Coverage then becomes
a measurable query — *"which rows are still unclassified?"* — instead of a
judgement call.

Three layers, each a ledger with one row per unit and a mandatory `status`:

| Layer | Denominator | File | Why |
|---|---|---|---|
| Methods / properties | 3,284 | `ledger_members.csv` | every callable = each line of logic |
| Event handlers (`Handles`) | 885 | `ledger_handlers.csv` | the *behavior* units (example 1 lives here) |
| Designer controls | 1,777 / 46 forms | `ledger_controls.csv` | layout + control-set (examples 2 & 3) |

LazWorks Library (the UI framework dependency) is **excluded** from the
denominator by decision — it is reimplemented natively in the port. It is
verified only at the *seams* where NIT calls into it (e.g. `FvMods.AddGroup`, the
ribbon, drag-drop), which show up as behaviors in the handler ledger.

## Status vocabulary

Verified states (set by a human during the sweep, or seeded from prior work):

- `Ported` — present in the port (possibly under a different name/structure).
- `Partial` — present but bounded/incomplete vs. the original.
- `Deferred` — intentionally not done yet; tracked in the handoff.
- `Divergence` — intentionally different (cross-platform / config-isolation).
- `MISSING` — a genuine, unintended gap. **This is the failure state.**

Machine-initial states (the queue to burn down):

- `AUTO-PORTED` — a name/comment match exists in the port → spot-check, then confirm `Ported`.
- `GAP?` — no match found → **investigate first**; classify into one of the verified states.
- `N/A` — framework/designer-generated noise (`New`/`Dispose`/`InitializeComponent`…).

**`GAP?` is triage, not a verdict.** It means "the auto-matcher found no
name/comment hit," which is deliberately over-inclusive. Empirically (see the
ProfileData calibration) most `GAP?` rows resolve to `Ported` (different name) or
`Deferred` (a known subsystem) — a minority are true `MISSING`. The value is that
the queue is *bounded and ranked*, not that every `GAP?` is a real gap.

## How to regenerate

```
cd docs/parity_audit
python extract_vb.py "<vb src>" ./out          # denominator CSVs
python build_ledger.py ./out "<port src>" .    # ledgers + DASHBOARD.md
```

`<vb src>`  = `.../NWN Installer Tool/NWN Installer Tool`
`<port src>` = `.../vaultkeeper/src`

`seeds.json` holds the known statuses (the 42 categorised dead ids + confirmed
findings); extend it as the sweep verifies rows, then regenerate.

## How to run the sweep

Work `DASHBOARD.md` top-down — files are ranked by `GAP?` density, so effort goes
where the unknowns concentrate.

For each VB file (one reviewable unit of work):

1. Open the VB file and its `GAP?` rows in `ledger_members.csv` / `_handlers.csv`.
2. For each row, find the port counterpart (grep the concept, not just the name —
   the port renames to snake_case and often restructures). Read both sides.
3. Set the row's `status` (+ a one-line `notes` and the port `port_hint`):
   `Ported` / `Partial` / `Deferred` / `Divergence` / `MISSING`.
4. Every `MISSING` (and `Partial` worth closing) becomes a fix task.
5. Re-run `build_ledger.py`; the file's `GAP?` count drops toward zero.

The audit is **done** for a file when it has no `GAP?` / `AUTO-PORTED` rows left —
every unit is either confirmed `Ported` or explicitly categorised. The audit is
done overall when that holds for every file, and the `MISSING` set is empty (or
each remaining `MISSING` is an accepted, documented decision).

Because each VB file is independent, the sweep parallelizes cleanly (one file per
reviewer/agent), but every classification must be verified against both sources —
never mark `Ported` on a name match alone.

## Findings log

Confirmed divergences are recorded in `DASHBOARD.md` (Findings section) and, once
turned into fixes, in the repo's normal history. The three design-time findings
above are seeded there as the first entries.
