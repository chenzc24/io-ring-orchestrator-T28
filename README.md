# io-ring-orchestrator-T28

A Claude Code skill for automated IO Ring generation on TSMC 28nm (T28) process nodes. Handles the complete workflow from natural-language requirements to verified layout — including JSON construction, Cadence SKILL generation, Virtuoso execution, and DRC/LVS/PEX verification.

---

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Installation](#installation)
4. [Configuration](#configuration)
   - [`.env` — Runtime Variables](#env--runtime-variables)
   - [`env_common.csh` — Calibre / PDK Paths](#env_commoncsh--calibre--pdk-paths)
5. [File Structure](#file-structure)
6. [Usage](#usage)
   - [Via Claude Code (Natural Language)](#via-claude-code-natural-language)
   - [Writing Effective Prompts](#writing-effective-prompts)
   - [Running the Built-in Wirebonding Test Cases](#running-the-built-in-wirebonding-test-cases)
   - [Via CLI Scripts](#via-cli-scripts)
7. [Workflow](#workflow)
8. [Layout Editor (Step 6)](#layout-editor-step-6)
9. [Output Files](#output-files)
9. [Troubleshooting](#troubleshooting)
10. [Related Documentation](#related-documentation)

---

## Overview

`io-ring-orchestrator-T28` is a self-contained Claude Code skill that automates TSMC 28nm IO Ring design. It bundles all required Python logic, SKILL templates, device data, and Calibre wrapper scripts — no separate package installation is needed.

**What it does:**
- Parses a natural-language IO Ring specification (signals, placement, dimensions)
- Classifies signals and maps them to T28 devices (`PDB3AC`, `PDDW16SDGZ`, `PCORNER_G`, etc.)
- Builds and validates an intent graph JSON
- Generates Cadence SKILL code for schematic and layout
- Executes SKILL in Virtuoso via the RAMIC bridge
- Runs Calibre DRC, LVS, and optionally PEX

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.7+ | Standard library sufficient for validation; full flow needs packages in `requirements.txt` |
| Cadence Virtuoso | Required for SKILL execution and screenshot capture |
| RAMIC bridge | Daemon that connects Claude Code to Virtuoso over TCP |
| Calibre (Mentor/Siemens) | Required for DRC, LVS, PEX — `MGC_HOME` must point to your installation |
| TSMC 28nm PDK | Layer map, LVS include files, and `cds.lib` are needed for verification |
| C shell (`csh`) | Calibre wrapper scripts are written in csh |

---

## Installation

### 1. Clone or copy the skill into your Claude Code skills directory

**Project-level (recommended for team use):**
```bash
# From your project root:
mkdir -p .claude/skills
cp -r io-ring-orchestrator-T28 .claude/skills/
```

**User-level (available across all projects):**
```bash
mkdir -p ~/.claude/skills
cp -r io-ring-orchestrator-T28 ~/.claude/skills/
```

Claude Code discovers skills by scanning the `.claude/skills/` directory at the project root and `~/.claude/skills/` for user-level skills. The skill is loaded when Claude Code starts in any project containing these paths.

### 2. Install Python dependencies

Run this from the skill destination directory after copying:

```bash
# Project-level install:
cd .claude/skills/io-ring-orchestrator-T28
pip install -r requirements.txt

# Or, user-level install:
cd ~/.claude/skills/io-ring-orchestrator-T28
pip install -r requirements.txt
```

### 3. Configure environment (see [Configuration](#configuration))

### 4. Start the RAMIC Bridge in Virtuoso

#### 4.1 SSH Port Forwarding
*(Required on code-development machines without direct access to the Virtuoso host)*

```bash
ssh -L RB_PORT:127.0.0.1:RB_PORT user@virtuoso_host
```

> `RB_PORT` must match the value set in `.env` (e.g. `65438`) and the port the RAMIC bridge daemon is listening on.

#### 4.2 Set Up the RAMIC Bridge

**Step 1 — Set the daemon path** *(once per terminal session, before launching Virtuoso's CIW):*

```bash
setenv RB_DAEMON_PATH /path/to/io-ring-orchestrator-T28/assets/external_scripts/ramic_bridge/ramic_bridge_daemon_27.py
```

**Step 2 — Load the bridge SKILL file** *(inside Virtuoso's CIW):*

```skill
load("/path/to/io-ring-orchestrator-T28/assets/external_scripts/ramic_bridge/ramic_bridge.il")
```

> A `t` return value in the CIW confirms successful loading.

The bridge listens on `RB_HOST:RB_PORT` (default `127.0.0.1:65438`).

### 5. Verify the installation

```bash
python3 scripts/check_virtuoso_connection.py
```

---

## Configuration

### `.env` — Runtime Variables

Create or edit `.env` in the skill root (`io-ring-orchestrator-T28/.env`). This file is loaded automatically by all CLI scripts.

```env
# === Required ===

# Path to your T28 cds.lib (used by Calibre strmout/si wrappers)
CDS_LIB_PATH_28=/absolute/path/to/your/T28/cds.lib

# === Virtuoso / RAMIC bridge ===

# Set to true to route SKILL calls through the RAMIC bridge
USE_RAMIC_BRIDGE=true

# RAMIC bridge host (usually localhost)
RB_HOST=127.0.0.1

# RAMIC bridge port (must match the port the bridge is listening on)
RB_PORT=65438

# === Optional output path controls ===

# 1) Explicit output root — highest priority.
#    All generated artifacts and reports will be written under this path.
#AMS_OUTPUT_ROOT=/absolute/path/to/workspace/output

# 2) Workspace root hint — used to derive output path when AMS_OUTPUT_ROOT is not set.
#    Scripts use ${AMS_IO_AGENT_PATH}/output as the output root.
#AMS_IO_AGENT_PATH=/absolute/path/to/workspace
```

**Variable reference:**

| Variable | Required | Default | Description |
|---|---|---|---|
| `CDS_LIB_PATH_28` | Yes | — | Absolute path to `cds.lib` for T28; read by Calibre csh wrappers |
| `USE_RAMIC_BRIDGE` | Yes | — | Enable RAMIC bridge mode (`true`/`1`/`yes`) |
| `RB_HOST` | No | `127.0.0.1` | RAMIC bridge host |
| `RB_PORT` | No | `65438` | RAMIC bridge port |
| `AMS_OUTPUT_ROOT` | No | `./output` | Explicit output root for all generated files |
| `AMS_IO_AGENT_PATH` | No | — | Workspace root; used to derive output path when `AMS_OUTPUT_ROOT` is not set |

**Output path resolution order:**
1. `AMS_OUTPUT_ROOT` (if set)
2. `${AMS_IO_AGENT_PATH}/output` (if `AMS_IO_AGENT_PATH` is set)
3. `$(pwd)/output` (current working directory fallback)

---

### `env_common.csh` — Calibre / PDK Paths

Located at `assets/external_scripts/calibre/env_common.csh`. This file is sourced by all Calibre wrapper scripts (`run_drc.csh`, `run_lvs.csh`, `run_pex.csh`). **Update the following paths to match your site installation before running DRC/LVS/PEX:**

```csh
# Calibre installation root
setenv MGC_HOME /home/mentor/calibre/calibre2022/aoj_cal_2022.1_36.16

# T28 PDK layer map (for strmout / XStream GDS export)
setenv PDK_LAYERMAP_28 /home/process/tsmc28n/PDK_mmWave/iPDK_CRN28HPC+ULL_v1.8_2p2a_20190531/tsmcN28/tsmcN28.layermap

# LVS include file for 28nm (lists additional source files for Calibre LVS)
setenv incFILE_28 /home/process/tsmc28n/PDK_mmWave/iPDK_CRN28HPC+ULL_v1.8_2p2a_20190531/tsmcN28/../Calibre/lvs/source.added
```

**Variables that need site-specific paths:**

| Variable | Description | Must be set by user |
|---|---|---|
| `MGC_HOME` | Calibre installation root | Yes |
| `PDK_LAYERMAP_28` | T28 PDK layer map file | Yes |
| `incFILE_28` | T28 LVS include file (`source.added`) | Yes |
| `CDS_LIB_PATH_28` | T28 `cds.lib` path | Set via `.env` or here |

Variables that are **auto-derived** and do not need manual editing:

| Variable | Value |
|---|---|
| `PDK_LAYERMAP_180` | T180 layer map (not used for T28 flow) |
| `incFILE_180` | T180 LVS include (not used for T28 flow) |
| `CALIBRE_RULE_FILE_28` | DRC rule file, relative to `calibre/` directory |
| `LVS_RULE_FILE_28` | LVS rule file, relative to `calibre/` directory |
| `DRC_RULE_FILE_28` | DRC rule file, relative to `calibre/` directory |
| `PEX_RUN_DIR` | Output directory for PEX runs |
| `DRC_RUN_DIR` | Output directory for DRC runs |
| `LVS_RUN_DIR` | Output directory for LVS runs |

---

## File Structure

```text
io-ring-orchestrator-T28/
│
├── .env                              # Runtime configuration (copy and edit this)
├── requirements.txt                  # Python dependencies
├── SKILL.md                          # Skill behavior contract and step-by-step workflow
├── README.md                         # This file
│
├── scripts/                          # CLI entry points
│   ├── validate_intent.py            # Validate intent graph JSON
│   ├── build_confirmed_config.py     # Convert intent JSON → confirmed config JSON
│   ├── generate_schematic.py         # Generate schematic SKILL (.il)
│   ├── generate_layout.py            # Generate layout SKILL (.il)
│   ├── check_virtuoso_connection.py  # Test RAMIC bridge / Virtuoso connectivity
│   ├── run_il_with_screenshot.py     # Execute SKILL in Virtuoso and capture screenshot
│   ├── run_drc.py                    # Run Calibre DRC
│   ├── run_lvs.py                    # Run Calibre LVS
│   ├── run_pex.py                    # Run Calibre PEX
│   └── README.md                     # Script-level argument reference
│
├── assets/
│   ├── core/                         # Core Python logic
│   │   ├── intent_graph/             # Intent graph schema and JSON validator
│   │   ├── layout/                   # Layout generation, device placement, SKILL codegen
│   │   │   ├── config/
│   │   │   │   └── lydevices_28.json # T28 layout device configuration
│   │   │   ├── layout_generator.py
│   │   │   ├── skill_generator.py
│   │   │   ├── confirmed_config_builder.py
│   │   │   └── ...
│   │   └── schematic/                # Schematic generation
│   │       └── schematic_generator_T28.py
│   │
│   ├── utils/                        # Bridge utilities and visualization helpers
│   │   ├── bridge_utils.py           # RAMIC bridge communication helpers
│   │   └── visualization.py          # Layout visualization utilities
│   │
│   ├── skill_code/                   # Cadence SKILL (.il) template files
│   │   ├── create_io_ring_lib_full.il
│   │   ├── create_schematic_cv.il
│   │   ├── helper_based_device_T28.il
│   │   ├── screenshot.il
│   │   └── get_cellview_info.il
│   │
│   ├── device_info/                  # T28 device data (templates + pin_rules)
│   │   └── IO_device_info_T28.json   # Device specifications and embedded pin_rules
│   │
│   └── external_scripts/
│       ├── calibre/                  # Calibre DRC/LVS/PEX csh wrappers
│       │   ├── env_common.csh        # Shared environment (edit PDK paths here)
│       │   ├── run_drc.csh
│       │   ├── run_lvs.csh
│       │   ├── run_pex.csh
│       │   └── T28/                  # T28-specific rule files
│       │       ├── _drc_rule_T28_cell_
│       │       ├── _calibre_T28.lvs_
│       │       ├── _calibre_T28.rcx_
│       │       └── si_T28.env
│       └── ramic_bridge/             # RAMIC bridge for Virtuoso communication
│           ├── ramic_bridge.il       # SKILL side of the bridge (load in Virtuoso CIW)
│           ├── ramic_bridge.py       # Python side of the bridge
│           ├── ramic_bridge_daemon_27.py  # Python 2.7-compatible daemon
│           └── README.md             # Bridge setup and protocol details
│
├── references/                       # Technology and flow references
│   ├── T28_Technology.md             # T28 device and process reference
│   ├── enrichment_rules_T28.md       # Intent graph enrichment rules
│   ├── draft_builder_T28.md          # Draft JSON construction reference
│   ├── wizard_T28.md                 # Wizard interaction guide
│   └── image_vision_instruction.md   # Screenshot interpretation guide
│
└── T28_Testbench/                    # Built-in wirebonding test cases
    ├── IO_28nm_<name>.txt            # Ready-made prompt files (paste into Claude Code)
    └── golden_output/
        └── IO_28nm_<name>/           # Reference outputs per test case
            ├── io_ring_intent_graph.json
            ├── io_ring_layout.il
            ├── io_ring_schematic.il
            ├── io_ring_layout_visualization.png
            ├── layout_screenshot.png
            └── schematic_screenshot.png
```

---

## Usage

### Via Claude Code (Natural Language)

Once the skill is installed, trigger it with a natural-language request in Claude Code:

```
Generate T28 IO ring with signals: VCM, CLKP, VDDIB, VSSIB, DA0, RST.
Clockwise placement, dimensions: top=2, bottom=2, left=2, right=2.
```

The skill handles all steps automatically. You can also explicitly invoke it:

```
Use io-ring-orchestrator-T28 to generate an IO ring with signals VCM, DA0, VDDIB, VSSIB.
```

---

### Writing Effective Prompts

The skill uses a rule-based enrichment engine to classify signals, select devices, and configure pin connections. Most decisions are driven by **signal names** and **voltage domain assignments**. Understanding these rules lets you write a prompt that produces the correct design on the first attempt.

#### How the skill classifies signals

| Signal type | How it's detected | Device assigned |
|---|---|---|
| Analog IO | Appears in a user-specified **analog voltage domain**, or name matches analog patterns (VCM, CLKP, VREF…) | `PDB3AC` |
| Analog power/ground provider | First VDD/VSS signal in a voltage domain range | `PVDD3AC` / `PVSS3AC` |
| Analog power/ground consumer | All other VDD/VSS signals in the same domain | `PVDD1AC` / `PVSS1AC` |
| Digital IO | Contiguous block of non-power signals not in any analog domain | `PDDW16SDGZ` |
| Digital power/ground | Exactly **4 unique signal names** forming the digital domain | `PVDD1DGZ` / `PVSS1DGZ` / `PVDD2POC` / `PVSS2DGZ` |
| Corner | Inferred from adjacent pad types | `PCORNER_G` (digital) or `PCORNERA_G` (analog/mixed) |

**Key implication**: if you have signals whose names look digital (e.g. `DVDD`, `GIOL`) but belong to an analog domain, you must state the domain explicitly — otherwise the skill may classify them as digital power.

#### What to include in your prompt

**Required for every design:**

- **Signal list** — all signal names in placement order
- **Pads per side** — number of pads on each edge (e.g. `3 pads per side`, or `top=4, bottom=4, left=2, right=2`)
- **Ring type** — `single ring` or `double ring`
- **Placement order** — `clockwise` or `counterclockwise` (default: counterclockwise)
- **Library and cell name** — Virtuoso target (e.g. `Library: LLM_Layout_Design, Cell: IO_RING_test`)

**Strongly recommended to avoid misclassification:**

- **Explicitly label signal types** — identify which signals are analog IO, analog power/ground, digital IO, and digital power/ground. Without this, the skill infers from name patterns, which may not match your naming convention.
- **Voltage domain assignment** — state which signals form each domain and which are the providers (VDD/VSS pair). This is the highest-priority input and overrides all name-based inference.
- **Digital domain names** — if your digital domain uses non-default names (i.e. not `VIOL/GIOL/VIOH/GIOH`), always specify them explicitly.
- **Signal direction** — for digital IO, specify `input` or `output` per signal if the name is ambiguous.

#### Minimal prompt

```
Generate T28 IO ring.
Signals: VIN VSSIB VDDIB VCM D1 D2 D3 D4 VIOL GIOL VIOH GIOH
4 pads per side, single ring, clockwise.
Library: LLM_Layout_Design, Cell: IO_RING_test.
```

> The skill will infer signal types and voltage domains automatically. Results are usually correct for standard naming conventions.

#### Full prompt (recommended)

```
Task: Generate IO ring schematic and layout for Cadence Virtuoso.

Design requirements:
4 pads per side. Single ring. Counterclockwise placement through left, bottom, right, top.

Signal names: VIN VSSIB VDDIB VCM D1 D2 D3 D4 VIOL GIOL VIOH GIOH

Signal classification:
- Analog IO: VIN, VCM
- Analog power/ground: VDDIB (VDD provider), VSSIB (VSS provider)
- Digital IO: D1, D2, D3, D4 (outputs)
- Digital power/ground: VIOL (low VDD), GIOL (low VSS), VIOH (high VDD), GIOH (high VSS)

Voltage domain:
- Analog domain: VDDIB/VSSIB (providers); VIN, VCM connect to this domain

Technology: 28nm process node
Library: LLM_Layout_Design
Cell name: IO_RING_4x4_single_ring_mixed
View: schematic and layout
```

> Explicit signal classification and voltage domain assignment guarantees the correct device selection and pin connections, especially when your signal names deviate from standard patterns.

---

### Running the Built-in Wirebonding Test Cases

The `T28_Testbench/` directory contains **30 ready-made test cases** covering a range of die sizes, ring types, and signal configurations. Use them to verify your installation or explore what the skill can do.

```
T28_Testbench/
├── IO_28nm_<name>.txt        ← prompt files (copy and paste directly into Claude Code)
└── golden_output/
    └── IO_28nm_<name>/       ← reference outputs (intent graph, layout .il, screenshots)
```

**To run a test case**, copy the contents of any `.txt` file and paste it as your prompt in Claude Code:

```bash
cat T28_Testbench/IO_28nm_3x3_single_ring_mixed.txt
```

Then paste the output into Claude Code. The skill will run the full pipeline and produce schematic + layout.

**Available test cases:**

| Case | Die size | Ring | Signal mix |
|---|---|---|---|
| `IO_28nm_3x3_single_ring_analog` | 3×3 | Single | Analog only |
| `IO_28nm_3x3_single_ring_digital` | 3×3 | Single | Digital only |
| `IO_28nm_3x3_single_ring_mixed` | 3×3 | Single | Mixed analog+digital |
| `IO_28nm_4x4_single_ring_*` | 4×4 | Single | Analog / Digital / Mixed |
| `IO_28nm_5x5_single_ring_*` | 5×5 | Single | Analog / Digital / Mixed |
| `IO_28nm_6x6_single_ring_*` | 6×6 | Single | Analog / Digital |
| `IO_28nm_7x7_single_ring_*` | 7×7 | Single | Analog / Digital |
| `IO_28nm_8x8_double_ring_*` | 8×8 | Double | Analog / Digital / Mixed / Multi-voltage |
| `IO_28nm_10x6_single_ring_mixed_*` | 10×6 | Single | Mixed (2 variants) |
| `IO_28nm_10x10_double_ring_multi_voltage_domain` | 10×10 | Double | Multi-voltage |
| `IO_28nm_12x12_*` | 12×12 | Single/Double | Mixed / Multi-voltage (4 variants) |
| `IO_28nm_12x18_*` | 12×18 | Double | Mixed / Multi-voltage |
| `IO_28nm_18x12_single_ring_mixed` | 18×12 | Single | Mixed |
| `IO_28nm_18x18_*` | 18×18 | Single/Double | Multi-voltage |

Compare your output against `golden_output/<case>/` to verify correctness.

### Via CLI Scripts

Scripts can be run independently for each pipeline step. Set the scripts path first:

```bash
export SCRIPTS_PATH="$(pwd)/scripts"
```

**Step-by-step example:**

```bash
# 1. Validate an intent graph JSON
python3 $SCRIPTS_PATH/validate_intent.py io_ring_intent_graph.json

# 2. Build confirmed configuration
python3 $SCRIPTS_PATH/build_confirmed_config.py intent.json confirmed.json T28 --skip-editor

# 3. Generate schematic SKILL code
python3 $SCRIPTS_PATH/generate_schematic.py confirmed.json schematic.il T28

# 4. Generate layout SKILL code
python3 $SCRIPTS_PATH/generate_layout.py confirmed.json layout.il T28

# 5. Check Virtuoso is reachable
python3 $SCRIPTS_PATH/check_virtuoso_connection.py

# 6. Execute SKILL and capture screenshot
python3 $SCRIPTS_PATH/run_il_with_screenshot.py layout.il MyLib MyCell screenshot.png layout

# 7. Run DRC
python3 $SCRIPTS_PATH/run_drc.py MyLib MyCell layout T28

# 8. Run LVS
python3 $SCRIPTS_PATH/run_lvs.py MyLib MyCell layout T28

# 9. Run PEX (optional)
python3 $SCRIPTS_PATH/run_pex.py MyLib MyCell layout
```

**Script exit codes:**

| Code | Meaning |
|---|---|
| 0 | Success / Pass |
| 1 | Failure / Verification fail |
| 2 | Setup error / File not found |

---

## Workflow

```
User Request
     │
     ▼
1. Parse input → create output directory
2. Build draft intent graph JSON (structural)
3. Enrich draft → final intent graph
4. Validate intent graph (validate_intent.py)
5. Build confirmed config (build_confirmed_config.py)
6. Generate schematic SKILL (generate_schematic.py)
7. Generate layout SKILL (generate_layout.py)
8. Check Virtuoso connection (check_virtuoso_connection.py)
9. Execute SKILL in Virtuoso + screenshot (run_il_with_screenshot.py)
10. Run DRC (run_drc.py)
11. Run LVS (run_lvs.py)
12. [Optional] Run PEX (run_pex.py)
     │
     ▼
Output files in output/generated/<timestamp>/
```

**T28 device types used:**

| Signal Type | Device |
|---|---|
| Analog IO | `PDB3AC` |
| Digital IO | `PDDW16SDGZ` |
| General corner | `PCORNER_G` |
| Analog corner | `PCORNERA_G` |

---

## Layout Editor (Step 6)

When the confirmed config is ready, the agent asks whether to open the **visual Layout Editor** before proceeding. If the user does not respond within a short timeout, the editor is **skipped automatically** and the auto-generated config is used directly.

### What the Editor Does

The Layout Editor is a **browser-based visual editor** launched on `localhost`. It renders the IO ring as an interactive SVG diagram where every pad, corner, and filler is a draggable, editable component. Users can review and adjust the placement, device assignment, and pin connections before the design is frozen into SKILL scripts.

> **How it works:** A local HTTP server injects the layout data into a self-contained React page. When the user clicks **"Confirm & Continue"**, the edited layout is POSTed back to the Python process, merged with the original structure, and written as the confirmed config JSON.

### Visual Conventions

Components are color-coded by category:

| Category | Color | Examples |
|----------|-------|---------|
| Analog IO / Power | Blue shades | `PDB3AC`, `PVDD3AC`, `PVSS1AC` |
| Digital IO / Power | Green shades | `PDDW16SDGZ`, `PVDD1DGZ`, `PVSS1DGZ` |
| Corners | Red shades | `PCORNERA_G` (analog), `PCORNER_G` (digital) |
| Fillers | Gray shades | `PFILLER10`, `PFILLER20` |
| Inner pads | Dashed border | Distinguishes inner ring pads from outer ring |

Each component displays a label in `signal_name : device_type` format.

### User Operations

| Operation | How |
|-----------|-----|
| **Select** | Click a component; Ctrl+Click for multi-select; drag a box for area selection |
| **Move** | Drag selected component(s) to reposition |
| **Edit properties** | Select a component → edit in the Inspector panel (name, device, pins, direction) |
| **Auto-fill pins** | Inspector panel button — fills pin connections from the device template |
| **Add component** | Toolbar "Add" menu — IO Pad, Filler, Cut, or Corner |
| **Delete** | Select component(s) → click Delete in toolbar |
| **Copy / Paste** | Ctrl+C / Ctrl+V |
| **Undo / Redo** | Ctrl+Z / Ctrl+Shift+Z |
| **Zoom / Pan** | Mouse wheel to zoom; middle-click drag to pan |
| **Import / Export JSON** | Toolbar buttons — load or save layout as JSON |
| **Confirm & Continue** | Toolbar button — finalize edits and return to the automated flow |

### Confirmation Flow

1. Agent asks: *"Open Layout Editor or Skip?"* (timeout → skip)
2. If opened → browser launches with the current layout rendered
3. User reviews, drags, edits as needed
4. User clicks **"Confirm & Continue"**
5. Edited data is merged back; auto-generated config proceeds to Step 7

---

## Output Files

All outputs are written to `${AMS_OUTPUT_ROOT}/generated/<YYYYMMDD_HHMMSS>/`:

| File | Description |
|---|---|
| `io_ring_intent_graph.json` | User intent specification (structured input) |
| `io_ring_confirmed.json` | Validated and enriched configuration |
| `io_ring_schematic.il` | Cadence SKILL code for schematic |
| `io_ring_layout.il` | Cadence SKILL code for layout |
| `schematic_screenshot.png` | Schematic view captured from Virtuoso |
| `layout_screenshot.png` | Layout view captured from Virtuoso |
| `drc_report.txt` | Calibre DRC results |
| `lvs_report.txt` | Calibre LVS results |
| `pex_report.txt` | Calibre PEX results (if run) |

---

## Troubleshooting

**Virtuoso connection fails:**
- Confirm Virtuoso is running: `ps aux | grep virtuoso`
- Confirm RAMIC bridge is loaded in Virtuoso CIW
- Verify `USE_RAMIC_BRIDGE`, `RB_HOST`, and `RB_PORT` in `.env`
- Test directly: `python3 scripts/check_virtuoso_connection.py`

**DRC/LVS script fails with path errors:**
- Verify `CDS_LIB_PATH_28` is set in `.env` or your shell environment
- Verify `MGC_HOME`, `PDK_LAYERMAP_28`, and `incFILE_28` in `env_common.csh`
- Ensure `csh` is available (`which csh`)

**Outputs written to unexpected location:**
- Explicitly set `AMS_OUTPUT_ROOT` in `.env`
- Check the output path resolution order in the [Configuration](#configuration) section

**Skill not triggering in Claude Code:**
- Use explicit phrasing: `Use io-ring-orchestrator-T28 to...`
- Verify `SKILL.md` exists at `io-ring-orchestrator-T28/SKILL.md`
- Check the skill directory is inside `.claude/skills/` or `~/.claude/skills/`

---

## Related Documentation

| Document | Location | Description |
|---|---|---|
| Skill contract | `SKILL.md` | Detailed workflow contract and step definitions |
| RAMIC bridge guide | `assets/external_scripts/ramic_bridge/README.md` | Bridge setup, protocol, and troubleshooting |
| T28 technology reference | `references/T28_Technology.md` | Device specifications and process details |
| Skills interface spec | `../../SKILL_INTERFACES.md` | Input/output interfaces for all skills |
