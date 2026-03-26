---
name: io-ring-orchestrator-T28
description: Master coordinator for complete T28 (28nm) IO Ring generation. Handles signal classification, device mapping, pin configuration, JSON generation, and complete workflow through DRC/LVS verification. Use this skill for any T28 IO Ring generation task.
---

# IO Ring Orchestrator - T28

You are the master coordinator for T28 IO Ring generation. You handle the **entire** workflow as a single skill — from parsing requirements through DRC/LVS verification.

## Scripts Path verification

```bash

SCRIPTS_PATH="/absolute_path/to/io-ring-orchestrator-T28/scripts"

# Verify:
ls "$SCRIPTS_PATH/validate_intent.py" || echo "ERROR: SCRIPTS_PATH not found"
```

## Entry Points

- **User provides text requirements only** → Start at Step 0, check wizard eligibility, ask user whether to enter Step 2, then continue (default skip to Step 3)
- **User provides image input (with or without text)** → Start at Step 0, then run Step 1 (Image Input Processing), check wizard eligibility, ask user whether to enter Step 2, then continue (default skip to Step 3)
- **User provides draft intent graph file** → Skip to Step 4 (Enrichment)
- **User provides final intent graph file** → Skip to Step 6 (Validation)
- Determine entry path automatically; only ask a wizard opt-in question when `wizard_eligible = true`

## Output Path Contract (Mandatory)

- Use a single workspace output root for the entire run.
- Create `output_dir` exactly once per run and reuse it for all Step 3-10 artifacts.
- Do not regenerate `timestamp` after Step 0.
- Export `AMS_OUTPUT_ROOT` once in Step 0 so script-level outputs remain deterministic.

Required conventions:

- `AMS_OUTPUT_ROOT`: workspace-level output root
- `output_dir`: per-run directory under `${AMS_OUTPUT_ROOT}/generated/${timestamp}`
- DRC/LVS reports: `${AMS_OUTPUT_ROOT}` and its fixed subdirs (`drc`, `lvs`)

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

After parsing, check wizard eligibility and ask user opt-in choice (see Step 2 below).

### Step 1: Image Input Processing Rules (Before Step 3)

Apply this step only when image input is provided.

Rules:

1. Load image-analysis instruction from `references/image_vision_instruction.md` first.
2. Use the instruction to extract structured requirements from image(s):
  - topology (Single/Double ring)
  - counter-clockwise outer-ring signal order
  - pad count description
  - inner-pad insertion directives (if Double Ring)
3. Treat extracted structure as Step 3 input. If user text and image conflict, prefer explicit user text constraints and keep unresolved conflicts explicit in the report.
4. Keep extraction/output conventions unchanged:
  - right side is read bottom-to-top
  - top side is read right-to-left
  - ignore `PFILLER*` devices

### Step 2: Interactive Wizard (Conditional, User Opt-In — Runs Between Step 1 and Step 3)

Full specification: `references/wizard_T28.md`

#### Orchestration Contract

After Step 0 (and Step 1 when image input exists), execute a two-stage decision using `references/wizard_T28.md` as the single source of truth:

1. Evaluate eligibility (`wizard_eligible`) from prompt characteristics.
2. If eligible, ask user opt-in and set `wizard_mode`.

Execution rules:

- Run wizard only when user explicitly opts in.
- If user skips wizard (or is not eligible), continue directly to Step 3.
- If wizard runs, execute all applicable phases exactly as defined in `references/wizard_T28.md`.

Output contract:

- Assemble `wizard_constraints` using the schema in `references/wizard_T28.md`.
- Treat `wizard_constraints` as Priority 1 explicit user specification in Step 4.
- Preserve structural inputs (signal list, dimensions, placement_order, inner-pad insertions) unchanged for Step 3.

### Step 3: Build Draft JSON (Structural Only)

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

- Do NOT add `device`, `pin_connection`, `direction`, or any `corner` instance in Step 3.

### Step 4: Enrich Draft JSON to Final Intent Graph

Read the Step 3 draft and enrich in a single pass.

Mandatory inputs for Step 4:

- Step 3 draft JSON (primary source for structural fields)
- Original user prompt (source for explicit intent not encoded structurally, such as voltage-domain assignment, provider naming, digital pin-domain naming, and direction overrides)
- `wizard_constraints` object if wizard was run in Step 2 (treated as Priority 1 — takes precedence over name-pattern inference, equivalent to explicit user specification)

Input precedence:

- Keep structural fields from Step 3 draft immutable (`ring_config`, `name`, `position`, `type`) unless a hard inconsistency is reported.
- Apply explicit user prompt constraints for domain/provider/direction naming when they do not conflict with immutable draft structure.

Primary reference:

- `references/enrichment_rules_T28.md`

Process:

1. Read `ring_config` and all draft instances (`name`, `position`, `type`) and user prompt constraints (including `wizard_constraints` if applicable).
2. Add per-instance `device` (and `direction` for digital IO).
3. Add per-instance `pin_connection`.
4. Insert 4 corners with correct type/order.
5. Run pre-save rule gates (must pass before saving), as defined in `references/enrichment_rules_T28.md`:
  - Continuity gate
  - Provider-count gate
  - Position-identity gate
  - Pin-family gate
  - VSS-consistency gate
6. Save final JSON to `{output_dir}/io_ring_intent_graph.json`.

Handoff rule:

- Treat draft structural fields as immutable unless a hard inconsistency must be reported.

### Step 5: Reference-Guided Gate Check (Mandatory)

Before Step 6 validation, explicitly verify Step 4 output against references:

- `references/enrichment_rules_T28.md` -> Priority, Domain Continuity, Position-Based Identity, Digital Provider Count
- `references/enrichment_rules_T28.md` -> Analog Pins, Digital Pins, Universal VSS Rule, Direction Rules
- `references/enrichment_rules_T28.md` -> Corner Rules

Also verify that Step 4 output preserves explicit constraints from the original user prompt (especially voltage-domain ranges, provider names, digital domain names, and direction overrides).

If any gate fails, repair JSON first and repeat Step 5. Do not proceed to Step 6.

### Step 6: Validate JSON

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
- Preserve Step 3 immutable fields (`ring_config`, `name`, `position`, `type`) during repair.
- Every fix must be traceable to an explicit validator error and a reference rule.
- If continuity/provider-count gates fail during repair, fix classification first, then device/pin labels.

### Step 7: Build Confirmed Config

```bash
python3 $SCRIPTS_PATH/build_confirmed_config.py \
  {output_dir}/io_ring_intent_graph.json \
  {output_dir}/io_ring_confirmed.json \
  T28 \
  --skip-editor
```

### Step 8: Generate SKILL Scripts

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

### Step 9: Check Virtuoso Connection

```bash
python3 $SCRIPTS_PATH/check_virtuoso_connection.py
```

- Exit 0 → proceed
- Exit 1 → **STOP**. Report all generated files so far and instruct user to start Virtuoso. Do NOT proceed.

### Step 10: Execute SKILL Scripts in Virtuoso

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

### Step 11: Run DRC

```bash
python3 $SCRIPTS_PATH/run_drc.py {lib} {cell} layout T28
```

- Exit 0 -> proceed to Step 12
- Exit 1 -> enter DRC repair loop:
  1. Read DRC report and extract failing rule/check locations.
  2. Map each error to reference rules (continuity/classification, device mapping, pin configuration, corner typing/order).
  3. Fix the source intent JSON first (`io_ring_intent_graph.json`), then re-run Step 7-11 to regenerate and recheck.
  4. Repeat until DRC passes, but allow at most 2 repair attempts; if still failing, stop and report the unresolved DRC blockers.

### Step 12: Run LVS

```bash
python3 $SCRIPTS_PATH/run_lvs.py {lib} {cell} layout T28
```

- Exit 0 -> proceed to Step 13
- Exit 1 -> enter LVS repair loop:
  1. Read LVS report and identify mismatch class (net mismatch, missing device, pin mismatch, shorts/opens).
  2. Query matching reference rules and locate the root cause in intent JSON (check continuity/provider-count gates before pin-level edits).
  3. Fix intent JSON by returning to Step 4 checks/fixes first, then re-run Step 4-13 (enrich, gate-check, validate, build, generate, execute, DRC, LVS, final report).
  4. Repeat until LVS passes, but allow at most 2 repair attempts; if still failing, stop and report the unresolved LVS blockers.

### Step 13: Final Report

Provide structured summary:
- Generated files (JSON, SKILL scripts, screenshots, reports) with paths
- Validation results (pass/fail)
- DRC/LVS results (if applicable)
- Ring statistics (total pads, analog/digital counts, voltage domains)
- Image analysis results (if layout analysis was performed)

## Task Completion Checklist

### Core Requirements
- [ ] All signals preserved (including duplicates), order strictly followed
- [ ] Step 3 draft JSON generated with only ring_config + name/position/type
- [ ] Step 4 enrichment completed (device/pin_connection/direction/corners)
- [ ] Step 4 reads draft JSON fields (name/position/type + ring_config), not name only

### Workflow
- [ ] Step 0: Timestamp directory created
- [ ] Step 2: Wizard eligibility evaluated, and user opt-in choice collected
- [ ] Step 2: If wizard active — run phases exactly per `references/wizard_T28.md` and assemble `wizard_constraints`
- [ ] Step 2: If wizard skipped — explicit prompt constraints carried directly to Step 4 as Priority 1
- [ ] Step 3: Draft intent graph generated and saved
- [ ] Step 4: Final intent graph generated from draft and saved
- [ ] Step 5: Reference-guided gate check passed
- [ ] Step 6: Validation passed (exit 0)
- [ ] Step 7: Confirmed config built
- [ ] Step 8: SKILL scripts generated
- [ ] Step 9: Virtuoso connection verified before execution
- [ ] Step 10: Scripts executed, screenshots saved
- [ ] Step 11: DRC completed
- [ ] Step 12: LVS completed
- [ ] Step 13: Final report delivered

## Troubleshooting

| Problem | Solution |
|---------|---------|
| Scripts not found | Use Option B (absolute path); verify with `ls $SCRIPTS_PATH/validate_intent.py` |
| Virtuoso not connected | Start Virtuoso; do NOT retry SKILL execution |
| Domain continuity fails | Re-classify signals using ring-wrap continuity first, then re-check digital provider count = 4 unique names |
| Validation failure | Enter Step 6 repair loop: parse error -> query matching rule in references -> apply targeted JSON fix -> re-validate; common issues: missing pins, wrong suffixes, duplicate indices |
| DRC failure | Enter Step 11 repair loop: parse DRC report -> query matching reference rules -> fix intent JSON -> regenerate and rerun DRC |
| LVS failure | Enter Step 12 repair loop: parse LVS mismatch -> return to Step 4 to check/fix intent JSON -> rerun Step 4-13 |

Repair loop cap (applies to Step 11/12):

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
