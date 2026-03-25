# IO Ring Orchestrator Scripts - T28 Skill

This directory contains standalone CLI scripts for T28 IO Ring generation.
All scripts are self-contained and use local imports from `assets/`.

## Overview

These scripts provide command-line access to IO Ring generation tools for T28 process node.
They are organized into two tiers:

### Tier 1: Standalone Scripts (No Dependencies)
- **validate_intent.py** - Validate intent graph JSON files
  - Uses Python stdlib only
  - Works without any external dependencies

### Tier 2: Core Tool Scripts
- **build_confirmed_config.py** - Build confirmed configuration
- **generate_schematic.py** - Generate schematic SKILL code
- **generate_layout.py** - Generate layout SKILL code
- **check_virtuoso_connection.py** - Check Virtuoso connectivity
- **run_il_with_screenshot.py** - Execute SKILL in Virtuoso
- **run_drc.py** - Run Design Rule Check
- **run_lvs.py** - Run Layout vs Schematic check

---

## Self-Contained Structure

This skill is fully self-contained - all code is bundled in `../assets/`:

```
../assets/
├── core/          # Core logic modules
├── utils/          # Utility functions (bridge, config, logging, etc.)
├── skill_code/     # Virtuoso SKILL files (.il)
├── device_info/    # Device templates
└── external_scripts/  # Calibre/ramic_bridge executables
```

**No external AMS-IO-Agent installation required.**

---

## Setup

### For Tier 1 (Validation Only)

No setup needed! Just run:
```bash
python3 validate_intent.py your_file.json
```

### For Tier 2 (Full Features)

No installation needed - all dependencies are bundled.

**Only external requirement:**
- Virtuoso bridge (skillbridge/ramic_bridge) - Install separately in your environment

---

## Usage Guide

### 1. Validate Intent Graph

```bash
python3 validate_intent.py io_ring_intent_graph.json
```

**Exit codes:**
- 0: Validation passed
- 1: Validation failed
- 2: File or JSON error

**Example output:**
```
✅ Intent graph validation passed!
   Validation passed: 52 pads, 0 corners
```

---

### 2. Build Confirmed Config

```bash
python3 build_confirmed_config.py \
    io_ring_intent_graph.json \
    io_ring_confirmed.json \
    T28
```

**Arguments:**
- `intent_graph.json` - Input intent graph file
- `output_confirmed.json` - Output confirmed config file
- `process_node` - Optional: T28 (default: T28)
- `--skip-editor` - Optional: Skip GUI confirmation

---

### 3. Generate Schematic

```bash
python3 generate_schematic.py \
    io_ring_confirmed.json \
    schematic.il \
    T28
```

**Arguments:**
- `config.json` - Input confirmed config file
- `output.il` - Output schematic SKILL file
- `process_node` - Optional: T28 (default: T28)

---

### 4. Generate Layout

```bash
python3 generate_layout.py \
    io_ring_confirmed.json \
    layout.il \
    T28
```

**Arguments:**
- `config.json` - Input confirmed config file
- `output.il` - Output layout SKILL file
- `process_node` - Optional: T28 (default: T28)

---

### 5. Check Virtuoso Connection

```bash
python3 check_virtuoso_connection.py
```

**Exit codes:**
- 0: Virtuoso is connected
- 1: Virtuoso not connected

**Example output:**
```
🔧 Checking Virtuoso connection...
✅ Virtuoso is running and accessible
   Response: test
```

---

### 6. Run SKILL with Screenshot

```bash
python3 run_il_with_screenshot.py \
    schematic.il \
    MyLib \
    MyCell \
    screenshot.png \
    schematic
```

**Arguments:**
- `il_file` - SKILL file to execute
- `lib` - Virtuoso library name
- `cell` - Virtuoso cell name
- `screenshot_path` - Optional: Output screenshot path
- `view` - Optional: schematic or layout (default: layout)

---

### 7. Run DRC

```bash
python3 run_drc.py MyLib MyCell layout T28
```

**Arguments:**
- `lib` - Virtuoso library name
- `cell` - Virtuoso cell name
- `view` - Optional: View name (default: layout)
- `tech_node` - Optional: T28 (default: T28)

**Exit codes:**
- 0: DRC passed
- 1: DRC failed

---

### 8. Run LVS

```bash
python3 run_lvs.py MyLib MyCell layout T28
```

**Arguments:**
- `lib` - Virtuoso library name
- `cell` - Virtuoso cell name
- `view` - Optional: View name (default: layout)
- `tech_node` - Optional: T28 (default: T28)

**Exit codes:**
- 0: LVS passed
- 1: LVS failed

---

## Complete Workflow Example

```bash
# Step 1: Validate intent graph
python3 validate_intent.py io_ring.json

# Step 2: Build confirmed config
python3 build_confirmed_config.py io_ring.json io_ring_confirmed.json T28

# Step 3: Generate schematic
python3 generate_schematic.py io_ring_confirmed.json schematic.il T28

# Step 4: Generate layout
python3 generate_layout.py io_ring_confirmed.json layout.il T28

# Step 5: Check Virtuoso
python3 check_virtuoso_connection.py

# Step 6: Execute schematic in Virtuoso
python3 run_il_with_screenshot.py schematic.il MyLib MyCell sch.png schematic

# Step 7: Execute layout in Virtuoso
python3 run_il_with_screenshot.py layout.il MyLib MyCell layout.png layout

# Step 8: Run DRC
python3 run_drc.py MyLib MyCell layout T28

# Step 9: Run LVS
python3 run_lvs.py MyLib MyCell layout T28
```

---

## Troubleshooting

### Error: Could not import core modules

**Check:** Verify `../assets/` directory exists and contains required modules:
```bash
ls ../assets/core/
ls ../assets/utils/
```

### Error: Virtuoso not connected

**Check:** Verify Virtuoso is running:
```bash
ps aux | grep virtuoso
```

**Check:** Verify bridge is running:
```bash
ps aux | grep ramic_bridge
# or
ps aux | grep skillbridge
```

### Error: SKILL file not found

**Check:** Verify SKILL files exist in `../assets/skill_code/`:
```bash
ls ../assets/skill_code/
```

### Error: DRC/LVS script not found

**Check:** Verify Calibre scripts exist in `../assets/external_scripts/calibre/`:
```bash
ls ../assets/external_scripts/calibre/
```

---

## Using from Claude Code Skills

Skills automatically reference these scripts:

```python
import subprocess
import sys

# Example: Validation
result = subprocess.run(
    [sys.executable, f"{skill_path}/scripts/validate_intent.py", json_file],
    capture_output=True,
    text=True
)

if result.returncode == 0:
    print("✅ Validation passed!")
else:
    print(f"❌ Validation failed:\n{result.stdout}")
```

---

## Script Features

All scripts include:
- ✅ Clear usage messages
- ✅ Proper error handling
- ✅ Exit codes (0=success, 1=failure, 2=setup error)
- ✅ Helpful error messages
- ✅ Progress indicators
- ✅ Direct imports from `../assets/` (no wrapper layer)

---

## Dependencies

### Tier 1 Scripts
- Python 3.7+ (stdlib only)

### Tier 2 Scripts
- Python 3.7+
- All core modules (bundled in `../assets/`)
- Virtuoso bridge (skillbridge/ramic_bridge) - Install separately

---

## File Organization

```
scripts/
├── README.md (this file)
│
├── validate_intent.py            (Tier 1 - Standalone)
│
├── build_confirmed_config.py     (Tier 2 - Core tools)
├── generate_schematic.py         (Tier 2 - Core tools)
├── generate_layout.py            (Tier 2 - Core tools)
├── check_virtuoso_connection.py (Tier 2 - Core tools)
├── run_il_with_screenshot.py     (Tier 2 - Core tools)
├── run_drc.py                   (Tier 2 - Core tools)
└── run_lvs.py                   (Tier 2 - Core tools)
```

---

## Architecture

**Import Chain:**
```
CLI Script → ../assets/core/*, ../assets/utils/*
```

No wrapper layers, no `runtime_t28.py`, no `io_ring_generator_tool.py`.
Each script directly imports from core modules and handles its own logic.

---

## Version

**Created:** 2026-03-20
**Skill Version:** Self-contained
**Process Node:** T28 (28nm)

---

## Documentation

For more information, see:
- Parent skill: `../SKILL.md`
- Knowledge base: `../references/T28_Technology.md`
- Reference docs: `../references/draft_builder_T28.md`, `../references/enrichement_rules_T28.md`
