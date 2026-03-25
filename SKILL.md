---
name: io-ring-orchestrator-T28
description: Master coordinator for complete T28 (28nm) IO Ring generation. Handles signal classification, device mapping, pin configuration, JSON generation, and complete workflow through DRC/LVS verification. Use this skill for any T28 IO Ring generation task.
---

# IO Ring Orchestrator - T28

You are the master coordinator for T28 IO Ring generation. You handle the **entire** workflow as a single skill — from parsing requirements through DRC/LVS verification.

## Self-Contained Skill Structure

This skill is fully self-contained:
- All core logic is in `assets/core/`
- All utilities are in `assets/utils/`
- All SKILL files are in `assets/skill_code/`
- All device info is in `assets/device_info/`
- All external scripts are in `assets/external_scripts/`
- All documentation is in `references/`

**No external AMS-IO-Agent installation required** — everything needed is bundled within this skill.

## Scripts Path Configuration

**CRITICAL:** Steps 4-9 use CLI wrapper scripts located in this skill's `scripts/` directory.

**Important:** Each script is self-contained and uses local imports from the skill's `assets/` directory. No external dependencies required.

```bash
# Option A: Auto-detect from skill directory
SCRIPTS_PATH="$(pwd)/scripts"

# Option B: Absolute path
SCRIPTS_PATH="/path/to/skill/T28/io-ring-orchestrator-T28/scripts"

# Verify:
ls "$SCRIPTS_PATH/validate_intent.py" || echo "ERROR: SCRIPTS_PATH not found"
```

## CLI Scripts

All scripts are self-contained and use local imports from `assets/`. No external dependencies required.

| Script | Purpose | Exit Codes |
|--------|---------|------------|
| `validate_intent.py <config.json>` | Validate intent graph JSON | 0=pass, 1=fail, 2=file error |
| `build_confirmed_config.py <in> <out> [node] [--skip-editor]` | Build confirmed config | 0=success, 1=error |
| `generate_schematic.py <config> <out> [node]` | Generate schematic SKILL | 0=success, 1=error |
| `generate_layout.py <config> <out> [node]` | Generate layout SKILL | 0=success, 1=error |
| `check_virtuoso_connection.py` | Check Virtuoso availability | 0=connected, 1=not connected |
| `run_il_with_screenshot.py <il> <lib> <cell> [screenshot] [view]` | Execute SKILL in Virtuoso | 0=success, 1=error |
| `run_drc.py <lib> <cell> [view] [tech]` | Run DRC verification | 0=pass, 1=fail |
| `run_lvs.py <lib> <cell> [view] [tech]` | Run LVS verification | 0=pass, 1=fail |
| `run_pex.py [lib] [cell] [view] [runDir]` | Run PEX extraction | 0=success, 1=fail |

## Entry Points

- **User provides text requirements only** → Start at Step 0, check wizard eligibility, ask user whether to enter Step 0.8, then continue (default skip to Step 1)
- **User provides image input (with or without text)** → Start at Step 0, then run Step 0.5 (Image Input Processing), check wizard eligibility, ask user whether to enter Step 0.8, then continue (default skip to Step 1)
- **User provides draft intent graph file** → Skip to Step 2 (Enrichment)
- **User provides final intent graph file** → Skip to Step 3 (Validation)
- Determine entry path automatically; only ask a wizard opt-in question when `wizard_eligible = true`

## Output Path Contract (Mandatory)

- Use a single workspace output root for the entire run.
- Create `output_dir` exactly once per run and reuse it for all Step 1-7 artifacts.
- Do not regenerate `timestamp` after Step 0.
- Export `AMS_OUTPUT_ROOT` once in Step 0 so script-level outputs remain deterministic.

Required conventions:

- `AMS_OUTPUT_ROOT`: workspace-level output root
- `output_dir`: per-run directory under `${AMS_OUTPUT_ROOT}/generated/${timestamp}`
- DRC/LVS/PEX reports: `${AMS_OUTPUT_ROOT}` and its fixed subdirs (`drc`, `lvs`, `pex*`)

## Complete Workflow

### Step 0: Directory Setup & Parse Input

```bash
# Resolve stable workspace root (prefer AMS_IO_AGENT_PATH, fallback to current directory)
if [ -n "${AMS_IO_AGENT_PATH:-}" ]; then
  WORK_ROOT="${AMS_IO_AGENT_PATH}"
else
  WORK_ROOT="$(pwd)"
fi

# Unified output root for script-level artifacts (DRC/LVS/PEX/screenshots fallback)
export AMS_OUTPUT_ROOT="${WORK_ROOT}/output"
mkdir -p "${AMS_OUTPUT_ROOT}/generated"

# Create per-run directory once and reuse it across all steps
if [ -n "${output_dir:-}" ] && [ -d "${output_dir}" ]; then
  echo "Reusing existing output_dir: ${output_dir}"
else
  timestamp="${timestamp:-$(date +%Y%m%d_%H%M%S)}"
  output_dir="${AMS_OUTPUT_ROOT}/generated/${timestamp}"
fi

mkdir -p "$output_dir"
echo "AMS_OUTPUT_ROOT=${AMS_OUTPUT_ROOT}"
echo "output_dir=${output_dir}"
```

Parse user input: signal list, ring dimensions (width × height), placement order, inner pad insertions, voltage domain specifications.

After parsing, check wizard eligibility and ask user opt-in choice (see Step 0.8 below).

### Step 0.5: Image Input Processing Rules (Before Step 1)

Apply this step only when image input is provided.

Rules:

1. Load image-analysis instruction from `references/image_vision_instruction.md` first.
2. If the reference file is missing or unreadable, fallback to the same built-in default instruction text.
3. Use the instruction to extract structured requirements from image(s):
  - topology (Single/Double ring)
  - counter-clockwise outer-ring signal order
  - pad count description
  - inner-pad insertion directives (if Double Ring)
4. Treat extracted structure as Step 1 input. If user text and image conflict, prefer explicit user text constraints and keep unresolved conflicts explicit in the report.
5. Keep extraction/output conventions unchanged:
  - right side is read bottom-to-top
  - top side is read right-to-left
  - ignore `PFILLER*` devices

### Step 0.8: Interactive Wizard (Conditional, User Opt-In — Runs Between Step 0.5 and Step 1)

Full specification: `references/wizard_T28.md`

#### Trigger Detection

After Step 0 (and Step 0.5 if image was provided), run a two-stage decision:

**Stage A — Eligibility gate (`wizard_eligible`)**

Set `wizard_eligible = true` only when ALL of the following are true:
- User provided a signal list in the prompt
- Prompt does NOT contain any explicit constraint indicators:
  - Device type keywords: `PDB3AC`, `PVDD3AC`, `PVSS3AC`, `PVDD1AC`, `PVSS1AC`, `PDDW16SDGZ`, `PVDD1DGZ`, `PVSS1DGZ`, `PVDD2POC`, `PVSS2DGZ`, `PVDD3A`, `PVSS3A`
  - Domain language: `voltage domain`, `domain`, `provider`, `consumer`
  - Explicit per-signal direction assignments: `input`, `output`

Set `wizard_eligible = false` when any of the following are true:
- User provided any of the above explicit constraint keywords → treat as Priority 1, go directly to Step 1
- User provided a draft or final intent graph file → go directly to Step 2 or Step 3
- User explicitly says "auto", "skip wizard", or "no wizard"

**Stage B — User choice (`wizard_mode`)**

Only if `wizard_eligible = true`, explicitly ask user whether to enter wizard mode:
- Option A: Enter wizard (run W1-W5)
- Option B: Skip wizard and continue with defaults to Step 1

Decision rule:
- `wizard_mode = true` only when user explicitly chooses Option A
- Otherwise `wizard_mode = false` and continue directly to Step 1 (default behavior)

#### Wizard Phases

When `wizard_mode = true`, run all applicable phases using `AskUserQuestion` before Step 1:

**Phase W1 — Signal Classification (always)**
- Auto-infer most likely type for each signal using name patterns from `references/wizard_T28.md`
- Present 4 signals per `AskUserQuestion` call (⌈N/4⌉ sequential calls)
- Each question: one signal per row, 4 type options, AI recommendation marked "(Recommended)"
- Collect confirmed type for every signal

**Phase W2 — Voltage Domain Grouping (skip if no analog signals)**
- Ask how many analog voltage domains (1 / 2 / 3+ / auto-detect pairs)
- If 2 domains: follow-up call with numbered signal list in preview pane, ask for split point
- If 3+: user types ranges in "Other" free-text
- Auto-assign providers: first VDD/VSS-named signal within each domain range

**Phase W3 — Digital Domain Provider Names (skip if no digital signals)**
- Ask: defaults (VIOL/GIOL/VIOH/GIOH) vs custom vs use signals from list
- If custom: user types 4 names in "Other" free-text (order: low_VDD, low_VSS, high_VDD, high_VSS)

**Phase W4 — Signal Directions (skip if no Digital IO signals)**
- Present 4 digital IO signals per call
- Each question: signal name + 2 options (Input / Output), AI recommendation from name pattern

**Phase W5 — Final Confirmation (always)**
- Show complete signal plan as formatted preview table
- Options: Generate now / Restart wizard / Type corrections manually / Cancel

#### Constraint Assembly

After all phases, assemble `wizard_constraints` object (schema in `references/wizard_T28.md`). This is injected into Step 2 enrichment as **Priority 1 explicit user specification**, overriding all auto-inference. The enrichment rules treat it exactly as if the user had typed full domain/type/direction specs in prose.

#### Handoff to Step 1

Pass the original structural inputs (signal list, dimensions, placement_order, inner-pad insertions) to Step 1 unchanged. `wizard_constraints` is carried forward to Step 2.

### Step 1: Build Draft JSON (Structural Only)

Build a draft JSON with only structural fields. No device/pin/corner inference in this step.

Primary reference:

- `references/draft_builder_T28.md`

Process:

1. Parse user structural inputs (signal list, width, height, placement_order, inner-pad insertions).
2. Compute `ring_config`.
3. Generate `instances` for `pad`/`inner_pad` with only:
  - `name`
  - `position`
  - `type`
4. Save draft to `{output_dir}/io_ring_intent_graph_draft.json`.

Strict boundary:

- Do NOT add `device`, `pin_connection`, `direction`, or any `corner` instance in Step 1.

### Step 2: Enrich Draft JSON to Final Intent Graph

Read the Step 1 draft and enrich in a single pass.

Mandatory inputs for Step 2:

- Step 1 draft JSON (primary source for structural fields)
- Original user prompt (source for explicit intent not encoded structurally, such as voltage-domain assignment, provider naming, digital pin-domain naming, and direction overrides)
- `wizard_constraints` object if wizard was run in Step 0.8 (treated as Priority 1 — takes precedence over name-pattern inference, equivalent to explicit user specification)

Input precedence:

- Keep structural fields from Step 1 draft immutable (`ring_config`, `name`, `position`, `type`) unless a hard inconsistency is reported.
- Apply explicit user prompt constraints for domain/provider/direction naming when they do not conflict with immutable draft structure.

Primary reference:

- `references/enrichment_rules_T28.md`

Process:

1. Read `ring_config` and all draft instances (`name`, `position`, `type`).
2. Add per-instance `device` (and `direction` for digital IO).
3. Add per-instance `pin_connection`.
4. Insert 4 corners with correct type/order.
5. Run pre-save rule gates (must pass before saving):
  - Continuity gate: apply ring-wrap continuity; digital block must be contiguous, and analog domains must be contiguous or explicitly split with per-block provider pairs.
  - Provider-count gate: digital provider names must be exactly 4 unique names (low VDD, low VSS, high VDD, high VSS).
  - Position-identity gate: repeated names must be resolved by position and per-domain range; never use global first-name lookup.
  - Pin-family gate: PVDD3A/PVSS3A use TAVDD/TAVSS; all other analog families use TACVDD/TACVSS.
  - VSS-consistency gate: all pads share the same `VSS` label, and that label differs from TACVSS/TAVSS labels.
6. Save final JSON to `{output_dir}/io_ring_intent_graph.json`.

Handoff rule:

- Treat draft structural fields as immutable unless a hard inconsistency must be reported.

### Step 2.5: Reference-Guided Gate Check (Mandatory)

Before Step 3 validation, explicitly verify Step 2 output against references:

- `references/enrichment_rules_T28.md` -> Priority, Domain Continuity, Position-Based Identity, Digital Provider Count
- `references/enrichment_rules_T28.md` -> Analog Pins, Digital Pins, Universal VSS Rule, Direction Rules
- `references/enrichment_rules_T28.md` -> Corner Rules

Also verify that Step 2 output preserves explicit constraints from the original user prompt (especially voltage-domain ranges, provider names, digital domain names, and direction overrides).

If any gate fails, repair JSON first and repeat Step 2.5. Do not proceed to Step 3.

### Step 3: Validate JSON

```bash
python3 $SCRIPTS_PATH/validate_intent.py {output_dir}/io_ring_intent_graph.json
```

- Exit 0 → proceed
- Exit 1 → enter repair loop:
  1. Read validator error messages carefully.
  2. Go back to references and query the matching rules (`references/draft_builder_T28.md` or `references/enrichment_rules_T28.md`).
  3. Apply targeted JSON fixes only for reported issues.
  4. Run validator again.
  5. Repeat until Exit 0 or a blocking inconsistency is found (then stop and report clearly).
- Exit 2 → file not found

Validation repair constraints:

- Do NOT regenerate the whole JSON unless structure is fundamentally broken.
- Preserve Step 1 immutable fields (`ring_config`, `name`, `position`, `type`) during repair.
- Every fix must be traceable to an explicit validator error and a reference rule.
- If continuity/provider-count gates fail during repair, fix classification first, then device/pin labels.

### Step 4: Build Confirmed Config

```bash
python3 $SCRIPTS_PATH/build_confirmed_config.py \
  {output_dir}/io_ring_intent_graph.json \
  {output_dir}/io_ring_confirmed.json \
  T28 \
  --skip-editor
```

### Step 5: Generate SKILL Scripts

```bash
python3 $SCRIPTS_PATH/generate_schematic.py \
  {output_dir}/io_ring_confirmed.json \
  {output_dir}/io_ring_schematic.il \
  T28

python3 $SCRIPTS_PATH/generate_layout.py \
  {output_dir}/io_ring_confirmed.json \
  {output_dir}/io_ring_layout.il \
  T28
```

### Step 6: Check Virtuoso Connection

```bash
python3 $SCRIPTS_PATH/check_virtuoso_connection.py
```

- Exit 0 → proceed
- Exit 1 → **STOP**. Report all generated files so far and instruct user to start Virtuoso. Do NOT proceed.

### Step 7: Execute SKILL Scripts in Virtuoso

```bash
python3 $SCRIPTS_PATH/run_il_with_screenshot.py \
  {output_dir}/io_ring_schematic.il \
  {lib} {cell} \
  {output_dir}/schematic_screenshot.png \
  schematic

python3 $SCRIPTS_PATH/run_il_with_screenshot.py \
  {output_dir}/io_ring_layout.il \
  {lib} {cell} \
  {output_dir}/layout_screenshot.png \
  layout
```

### Step 8: Run DRC

```bash
python3 $SCRIPTS_PATH/run_drc.py {lib} {cell} layout T28
```

- Exit 0 -> proceed to Step 9
- Exit 1 -> enter DRC repair loop:
  1. Read DRC report and extract failing rule/check locations.
  2. Map each error to reference rules (continuity/classification, device mapping, pin configuration, corner typing/order).
  3. Fix the source intent JSON first (`io_ring_intent_graph.json`), then re-run Step 4-8 to regenerate and recheck.
  4. Repeat until DRC passes, but allow at most 2 repair attempts; if still failing, stop and report the unresolved DRC blockers.

### Step 9: Run LVS

```bash
python3 $SCRIPTS_PATH/run_lvs.py {lib} {cell} layout T28
```

- Exit 0 -> proceed to Step 10
- Exit 1 -> enter LVS repair loop:
  1. Read LVS report and identify mismatch class (net mismatch, missing device, pin mismatch, shorts/opens).
  2. Query matching reference rules and locate the root cause in intent JSON (check continuity/provider-count gates before pin-level edits).
  3. Fix intent JSON by returning to Step 2 checks/fixes first, then re-run Step 2-10 (enrich, gate-check, validate, build, generate, execute, DRC, LVS, final report).
  4. Repeat until LVS passes, but allow at most 2 repair attempts; if still failing, stop and report the unresolved LVS blockers.

### Step 9.5 (Optional): Run PEX Extraction

```bash
python3 $SCRIPTS_PATH/run_pex.py {lib} {cell} layout
```

- This step is optional and may be requested for parasitic extraction analysis
- PEX generates netlist with parasitic capacitance information


DRC/LVS/PEX repair constraints:

- Do NOT patch generated IL directly; always repair intent JSON and regenerate outputs.
- Prioritize fixes in this order: corner type/order -> inner_pad positioning -> domain continuity/classification -> device type/suffix -> pin_connection labels -> domain/provider assignment.
- If digital classification is non-contiguous (ring-wrapped), re-classify before pin/device fixes.
- Each repair must cite one concrete report error and one matching reference rule.

### Step 10: Final Report

Provide structured summary:
- Generated files (JSON, SKILL scripts, screenshots, reports) with paths
- Validation results (pass/fail)
- DRC/LVS/PEX results (if applicable)
- Ring statistics (total pads, analog/digital counts, voltage domains)
- Image analysis results (if layout analysis was performed)

## Task Completion Checklist

### Core Requirements
- [ ] All signals preserved (including duplicates), order strictly followed
- [ ] Step 1 draft JSON generated with only ring_config + name/position/type
- [ ] Step 2 enrichment completed (device/pin_connection/direction/corners)
- [ ] Step 2 reads draft JSON fields (name/position/type + ring_config), not name only

### Device & Configuration
- [ ] Voltage-domain classification is correct and user analog-domain assignment has top priority
- [ ] Digital provider count is exactly 4 unique names (low VDD, low VSS, high VDD, high VSS)
- [ ] Position-based identity is used for repeated names (no global first-name lookup)
- [ ] Same signal name across different domains is resolved by per-domain range, never global-first occurrence
- [ ] Provider signals use PVDD3AC/PVSS3AC (or PVDD3A/PVSS3A only when user-specified), NOT PDB3AC
- [ ] Same-name providers across different analog domains are selected per-domain by range, not globally
- [ ] Device suffixes are correct: _H_G for left/right, _V_G for top/bottom
- [ ] Analog IO (PDB3AC): AIO -> signal_name (NOT _CORE)
- [ ] Analog provider AVDD/AVSS -> signal_name_CORE (bus format: prefix_CORE<index>)
- [ ] Analog pin families are correct: PVDD3A/PVSS3A use TAVDD/TAVSS, all other analog families use TACVDD/TACVSS
- [ ] All digital pads (including digital IO and digital power/ground) have exactly 4 pins: VDD/VSS/VDDPST/VSSPST, no AIO
- [ ] `direction` field is present at instance top level for all digital IO (PDDW16SDGZ)
- [ ] VSS pin uses the same signal name across ALL pads and is different from TACVSS/TAVSS labels
- [ ] Domain continuity checks pass with ring-wrap semantics (analog blocks and digital block)
- [ ] If digital continuity fails, perform classification repair first (do not force-fit pins/devices)
- [ ] If one analog domain is split into multiple blocks, each block has its own provider pair or is explicitly user-defined
- [ ] Corner types correctly determined:
  - [ ] All 4 corners present (top_left, top_right, bottom_left, bottom_right)
  - [ ] Corner types: PCORNER_G (both adjacent digital), PCORNERA_G (analog or mixed)
  - [ ] Corner insertion order matches placement_order

### Workflow
- [ ] Step 0: Timestamp directory created
- [ ] Step 0.8: Wizard eligibility evaluated, and user opt-in choice collected
- [ ] Step 0.8: If wizard active — all applicable phases (W1–W5) completed and wizard_constraints assembled
- [ ] Step 0.8: If wizard skipped — explicit prompt constraints carried directly to Step 2 as Priority 1
- [ ] Step 1: Draft intent graph generated and saved
- [ ] Step 2: Final intent graph generated from draft and saved
- [ ] Step 3: Validation passed (exit 0)
- [ ] Step 4: Confirmed config built
- [ ] Step 5: SKILL scripts generated
- [ ] Step 6: Virtuoso connection verified before execution
- [ ] Step 7: Scripts executed, screenshots saved
- [ ] Step 8: DRC completed
- [ ] Step 9: LVS completed
- [ ] Step 9.5: PEX completed (if requested)
- [ ] Step 10: Final report delivered

## Troubleshooting

| Problem | Solution |
|---------|---------|
| Scripts not found | Use Option B (absolute path); verify with `ls $SCRIPTS_PATH/validate_intent.py` |
| Virtuoso not connected | Start Virtuoso; do NOT retry SKILL execution |
| Domain continuity fails | Re-classify signals using ring-wrap continuity first, then re-check digital provider count = 4 unique names |
| Validation failure | Enter Step 3 repair loop: parse error -> query matching rule in references -> apply targeted JSON fix -> re-validate; common issues: missing pins, wrong suffixes, duplicate indices |
| DRC failure | Enter Step 8 repair loop: parse DRC report -> query matching reference rules -> fix intent JSON -> regenerate and rerun DRC |
| LVS failure | Enter Step 9 repair loop: parse LVS mismatch -> return to Step 2 to check/fix intent JSON -> rerun Step 2-10 |

Repair loop cap (applies to Step 8/9):

- Maximum 2 repair attempts per loop. If still failing after attempt 2, stop the loop and report unresolved blockers.

## Directory Structure

```
io-ring-orchestrator-T28/
├── SKILL.md                          # This file
├── requirements.txt                   # Python requirements (minimal)
│
├── scripts/                          # CLI entry point scripts (each self-contained)
│   ├── validate_intent.py
│   ├── build_confirmed_config.py
│   ├── generate_schematic.py
│   ├── generate_layout.py
│   ├── check_virtuoso_connection.py
│   ├── run_il_with_screenshot.py
│   ├── run_drc.py
│   ├── run_lvs.py
│   ├── run_pex.py
│   └── README.md
│
├── references/                       # Documentation & templates
│   ├── draft_builder_T28.md
│   ├── enrichment_rules_T28.md
│   ├── T28_Technology.md
│   ├── intent_graph_minimal.json
│   ├── intent_graph_template.json
│   └── image_vision_instruction.md
│
└── assets/                          # All bundled code (self-contained)
    ├── core/                         # Core logic
    │   ├── layout/                    # Layout generation modules
    │   │   ├── layout_generator.py      # T28 layout generator
    │   │   ├── confirmed_config_builder.py
    │   │   ├── skill_generator.py
    │   │   ├── auto_filler.py
    │   │   ├── layout_visualizer.py
    │   │   ├── inner_pad_handler.py
    │   │   ├── device_classifier.py
    │   │   ├── position_calculator.py
    │   │   ├── process_node_config.py
    │   │   ├── layout_generator_factory.py
    │   │   ├── filler_generator.py
    │   │   ├── layout_validator.py
    │   │   ├── voltage_domain.py
    │   │   ├── editor_confirm_merge.py
    │   │   └── editor_utils.py
    │   ├── schematic/
    │   │   ├── schematic_generator_T28.py
    │   │   └── devices/
    │   │       └── IO_device_info_T28_parser.py
    │   └── intent_graph/
    │       └── json_validator.py
    │
    ├── utils/                        # Utility modules
    │   ├── bridge_utils.py           # Virtuoso bridge
    │   ├── logging_utils.py
    │   ├── visualization.py
    │   └── banner.py
    │
    ├── skill_code/                   # Virtuoso SKILL files (.il)
    │   ├── screenshot.il
    │   ├── get_cellview_info.il
    │   ├── helper_based_device_T28.il
    │   ├── create_io_ring_lib_full.il
    │   └── create_schematic_cv.il
    │
    ├── device_info/                  # Device templates
    │   ├── IO_device_info_T28.json
    │   ├── IO_device_info_T28.txt
    │   ├── IO_device_pin_rules_T28.json
    │   └── IO_device_info_T28_parser.py
    │
    └── external_scripts/             # External executables
        ├── calibre/
        │   ├── T28/
        │   ├── run_drc.csh
        │   ├── run_lvs.csh
        │   └── run_pex.csh
        └── ramic_bridge/
            ├── ramic_bridge.py
            ├── ramic_bridge.il
            └── ramic_bridge_daemon_27.py
```
