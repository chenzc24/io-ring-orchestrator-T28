# Complete Call Flow After Migration
# io-ring-orchestrator-T28 → virtuoso-bridge-lite Only

> All four scripts call only `bridge_utils.py`.
> `bridge_utils.py` is the **single integration point** with virtuoso-bridge-lite.
> No script imports from virtuoso-bridge-lite directly — except one local function
> in `run_pex.py` that is also cleaned up (see §4).

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    Scripts (unchanged callers)                   │
│  run_il_with_screenshot.py  run_drc.py  run_lvs.py  run_pex.py │
└──────────────────────────┬──────────────────────────────────────┘
                           │  imports
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│              assets/utils/bridge_utils.py  (rewritten)          │
│                                                                  │
│  _get_client() ──────────────────────► VirtuosoClient.from_env()│
│  rb_exec(skill)  ────────────────────► client.execute_skill()   │
│  load_skill_file(path) ──────────────► client.load_il(path)     │
│  execute_csh_script(script, *args) ──► SSHClient.upload_file()  │
│                                        SSHClient.run_command()  │
└─────────────────────────────────────────────────────────────────┘
                           │
              ┌────────────┴─────────────┐
              ▼                          ▼
   VirtuosoClient                    SSHClient
   (SKILL execution)            (file upload + shell)
        │                               │
        │ TCP                           │ SSH
        ▼                               ▼
  Virtuoso Daemon               EDA Server Shell
  (RAMIC protocol)         (csh, Calibre, filesystem)
        │
        ▼
  Virtuoso CIW / SKILL
```

**Two transport paths, both from virtuoso-bridge-lite:**

| Transport | API | Used for |
|---|---|---|
| TCP → Virtuoso daemon | `VirtuosoClient.execute_skill()` | SKILL commands, cellView ops, screenshot |
| SSH | `SSHClient.upload_file()` + `run_command()` | Upload `.il`/`.csh`, run Calibre |

---

## 1. `run_il_with_screenshot.py`

### What it calls from `bridge_utils`
```python
from assets.utils.bridge_utils import (
    open_cell_view_by_type,       # open cellView in Virtuoso
    ge_open_window,               # open graphical window
    ui_redraw,                    # redraw Virtuoso UI
    rb_exec,                      # sync cv variable
    save_current_cellview,        # save after IL execution
    load_script_and_take_screenshot,  # upload screenshot.il + capture PNG
)
```
Plus: `run_il_file()` (local to the script) calls `load_skill_file()` via `rb_exec`.

### Full call chain after migration

```
run_il_with_screenshot.py::main()
│
├─ run_il_file(il_file, lib, cell, view)
│   │
│   ├─ open_cell_view_by_type(lib, cell, "layout", mode="w")
│   │       │
│   │       └─ rb_exec('cv = dbOpenCellViewByType("lib" "cell" "layout" ...)')
│   │               │
│   │               └─ _get_client()
│   │                       └─ VirtuosoClient.from_env()   [SSH tunnel]
│   │               │
│   │               └─ client.execute_skill(skill, timeout=30)
│   │                       └─► TCP → Virtuoso daemon → SKILL evaluates
│   │                           dbOpenCellViewByType() → returns cv object
│   │
│   ├─ ge_open_window(lib, cell, "layout", mode="a")
│   │       └─ rb_exec('window = geOpen(?lib "lib" ?cell "cell" ...)')
│   │               └─► TCP → Virtuoso → opens layout editor window
│   │
│   ├─ ui_redraw()
│   │       └─ rb_exec('hiRedraw()')
│   │               └─► TCP → Virtuoso → redraws display
│   │
│   ├─ rb_exec('cv = geGetEditCellView()')
│   │       └─► TCP → Virtuoso → syncs cv variable to current edit view
│   │
│   ├─ load_skill_file("io_ring_layout.il", timeout=60)
│   │       │
│   │       └─ client.load_il("/local/path/io_ring_layout.il")
│   │               │
│   │               ├─ _prepare_il_path():
│   │               │   tunnel is active → SSH upload:
│   │               │   upload_text(content) → /tmp/vb_<user>/io_ring_layout.il
│   │               │
│   │               └─ execute_skill('load("/tmp/vb_<user>/io_ring_layout.il")')
│   │                       └─► TCP → Virtuoso CIW → executes layout SKILL code
│   │                           IO Ring layout is created in Virtuoso ✓
│   │
│   └─ save_current_cellview()
│           └─ rb_exec('dbSave(cv)')
│                   └─► TCP → Virtuoso → saves the cellView to disk ✓
│
├─ ui_redraw() + ui_zoom_absolute_scale(0.9)
│       └─► TCP → Virtuoso → cosmetic display updates
│
└─ load_script_and_take_screenshot("screenshot.il", "layout_screenshot.png")
        │
        └─ load_script_and_take_screenshot_verbose(...)
                │
                ├─ client.load_il("assets/skill_code/screenshot.il")
                │       │
                │       ├─ SSH upload → /tmp/vb_<user>/screenshot.il
                │       └─ execute_skill('load("/tmp/vb_<user>/screenshot.il")')
                │               └─► TCP → Virtuoso → defines takeScreenshot() ✓
                │
                └─ rb_exec('takeScreenshot("/path/layout_screenshot.png")')
                        └─► TCP → Virtuoso → PNG written to server filesystem ✓
                            (accessible locally via NFS or shared mount)

Result: layout created in Virtuoso + layout_screenshot.png saved ✓
```

---

## 2. `run_drc.py`

### What it calls from `bridge_utils`
```python
from assets.utils.bridge_utils import (
    open_cell_view_by_type,   # open layout cellView (read mode)
    ui_redraw,                # redraw UI
    execute_csh_script,       # upload + run run_drc.csh on server
)
```

### Full call chain after migration

```
run_drc.py::main()
│
├─ open_cell_view_by_type(lib, cell, "layout", mode="r")
│       └─ rb_exec('cv = dbOpenCellViewByType("lib" "cell" "layout" ... "r")')
│               └─► TCP → Virtuoso → opens layout for reading (GDS export) ✓
│
├─ ui_redraw()
│       └─► TCP → Virtuoso → refreshes view ✓
│
└─ execute_csh_script("run_drc.csh", lib, cell, "layout", "T28", timeout=300)
        │
        ├─ SSHClient.from_env()   [reuses existing tunnel]
        │
        ├─ ssh.upload_file(env_common.csh  → /tmp/vb_t28_calibre/env_common.csh)
        ├─ ssh.upload_file(run_drc.csh     → /tmp/vb_t28_calibre/run_drc.csh)
        ├─ ssh.upload_file(T28/_drc_rule_  → /tmp/vb_t28_calibre/T28/_drc_rule_)
        ├─ ssh.upload_file(T28/... more rule files ...)
        │       All uploaded via tar pipe over SSH ✓
        │
        └─ ssh.run_command(
               "chmod +x /tmp/vb_t28_calibre/run_drc.csh && "
               "AMS_OUTPUT_ROOT=... csh /tmp/vb_t28_calibre/run_drc.csh "
               "lib cell layout T28"
           )
               └─► SSH → Calibre runs on EDA server
                   DRC executes against the layout GDS ✓
                   Returns CommandResult(returncode, stdout, stderr)

After: parse DRC summary → write local report file → print pass/fail ✓
```

---

## 3. `run_lvs.py`

### What it calls from `bridge_utils`
```python
from assets.utils.bridge_utils import (
    open_cell_view_by_type,
    ui_redraw,
    execute_csh_script,       # upload + run run_lvs.csh on server
)
```

### Full call chain after migration

```
run_lvs.py::main()
│
├─ open_cell_view_by_type(lib, cell, "layout", mode="r")
│       └─► TCP → Virtuoso → opens layout for LVS export ✓
│
├─ ui_redraw()
│       └─► TCP → Virtuoso ✓
│
└─ execute_csh_script("run_lvs.csh", lib, cell, "layout", "T28", timeout=300)
        │
        ├─ SSHClient.from_env()
        │
        ├─ ssh.upload_file(env_common.csh  → /tmp/vb_t28_calibre/env_common.csh)
        ├─ ssh.upload_file(run_lvs.csh     → /tmp/vb_t28_calibre/run_lvs.csh)
        ├─ ssh.upload_file(T28/_calibre_T28.lvs_ → /tmp/vb_t28_calibre/T28/...)
        ├─ ssh.upload_file(T28/si_T28.env  → /tmp/vb_t28_calibre/T28/si_T28.env)
        │
        └─ ssh.run_command("csh /tmp/vb_t28_calibre/run_lvs.csh lib cell layout T28")
               └─► SSH → Calibre LVS runs on EDA server ✓
                   Returns CommandResult(returncode, stdout, stderr)

After: parse LVS summary → write local report file → print pass/fail ✓
```

---

## 4. `run_pex.py`

### Important: local `get_current_design()` must also be cleaned up

`run_pex.py` defines a **local copy** of `get_current_design()` that still calls
`use_ramic_bridge()` and the skillbridge fallback. This function must be replaced
with a direct import from `bridge_utils`:

```python
# BEFORE (in run_pex.py, lines 80-116) — DELETE this local function:
def get_current_design():
    from assets.utils.bridge_utils import use_ramic_bridge, rb_exec
    if use_ramic_bridge():
        ...
    else:
        from skillbridge import Workspace  # skillbridge fallback
        ...

# AFTER — replace the local function and its call with a direct import:
from assets.utils.bridge_utils import get_current_design
```

### What it calls from `bridge_utils` (after cleanup)
```python
from assets.utils.bridge_utils import (
    open_cell_view_by_type,
    ui_redraw,
    execute_csh_script,       # upload + run run_pex.csh on server
    get_current_design,       # replaces the now-deleted local copy
)
```

### Full call chain after migration

```
run_pex.py::main()
│
├─ [if lib/cell provided]
│   open_cell_view_by_type(lib, cell, "layout", mode="r")
│           └─► TCP → Virtuoso → opens layout ✓
│
├─ [if lib/cell NOT provided]
│   get_current_design()    ← imported from bridge_utils (not local copy)
│           └─ rb_exec('sprintf(nil "%s" ddGetObjReadPath(...))')
│                   └─► TCP → Virtuoso → returns current cellView path ✓
│
├─ ui_redraw()
│       └─► TCP → Virtuoso ✓
│
└─ execute_csh_script("run_pex.csh", lib, cell, "layout", "T28", pex_dir, timeout=300)
        │
        ├─ SSHClient.from_env()
        │
        ├─ ssh.upload_file(env_common.csh  → /tmp/vb_t28_calibre/env_common.csh)
        ├─ ssh.upload_file(run_pex.csh     → /tmp/vb_t28_calibre/run_pex.csh)
        ├─ ssh.upload_file(T28/_calibre_T28.rcx_ → /tmp/vb_t28_calibre/T28/...)
        ├─ ssh.upload_file(T28/si_T28.env  → /tmp/vb_t28_calibre/T28/si_T28.env)
        │
        └─ ssh.run_command(
               "csh /tmp/vb_t28_calibre/run_pex.csh "
               "lib cell layout T28 /path/to/pex_dir"
           )
               └─► SSH → Calibre PEX runs on EDA server ✓
                   Generates: cell.pex.netlist, PIPO.LOG.cell
                   Returns CommandResult(returncode, stdout, stderr)

After: parse PEX netlist → write local report file → print parasitic summary ✓
```

---

## 5. What Changes vs What Stays the Same

### Scripts — UNCHANGED (except `run_pex.py`)

| Script | Change needed |
|---|---|
| `run_il_with_screenshot.py` | None — all imports from bridge_utils |
| `run_drc.py` | None — all imports from bridge_utils |
| `run_lvs.py` | None — all imports from bridge_utils |
| `run_pex.py` | **Remove local `get_current_design()`** (lines 80–116); import from bridge_utils instead |

### `bridge_utils.py` — rewritten internally, same public API

Every public function keeps its name and signature. Internal implementation replaces
the bundled bridge calls with virtuoso-bridge-lite calls:

| Function | Before (bundled bridge) | After (virtuoso-bridge-lite) |
|---|---|---|
| `rb_exec(skill)` | `RBExc(skill, host, port)` → strip control chars | `client.execute_skill(skill)` → `result.output` |
| `load_skill_file(path)` | `rb_exec('load("path")')` — no upload | `client.load_il(path)` — SSH upload + load |
| `open_cell_view_by_type(...)` | SKILL snippet via `rb_exec` | Same SKILL snippet via `rb_exec` (simplified) |
| `ge_open_window(...)` | SKILL snippet via `rb_exec` | Same SKILL snippet via `rb_exec` (simplified) |
| `open_cell_view(...)` | SKILL snippet via `rb_exec` | Same SKILL snippet via `rb_exec` (simplified) |
| `save_current_cellview()` | `rb_exec('dbSave(cv)')` | `rb_exec('dbSave(cv)')` (simplified) |
| `ui_redraw()` | `rb_exec('hiRedraw()')` | `rb_exec('hiRedraw()')` (simplified) |
| `ui_zoom_absolute_scale(s)` | `rb_exec('hiZoomAbsoluteScale(...)')` | Same via `rb_exec` (simplified) |
| `get_current_design()` | `rb_exec(...)` or skillbridge | `rb_exec(...)` only (simplified) |
| `load_script_and_take_screenshot_verbose(...)` | `rb_exec('load(...)')` — no upload | `client.load_il(path)` — SSH upload + load |
| `execute_csh_script(script, *args)` | SKILL `csh("...")` via `rb_exec` | SSH upload + `ssh.run_command()` |

### `_get_client()` — new private helper, replaces `_import_rbexc()` + `use_ramic_bridge()`

```python
def _get_client():
    from virtuoso_bridge import VirtuosoClient
    from pathlib import Path
    from dotenv import load_dotenv
    # Pre-load ~/.virtuoso-bridge/.env so VB vars take priority over T28's .env
    _vb_env = Path.home() / ".virtuoso-bridge" / ".env"
    if _vb_env.is_file():
        load_dotenv(_vb_env, override=True)
    return VirtuosoClient.from_env()
```

---

## 6. User Setup (one-time)

```
1. Install virtuoso-bridge-lite:
   pip install -e /path/to/virtuoso-bridge-lite

2. Configure connection:
   virtuoso-bridge init          # creates ~/.virtuoso-bridge/.env
   # Edit ~/.virtuoso-bridge/.env: VB_REMOTE_HOST, VB_REMOTE_USER, etc.

3. Start tunnel + deploy daemon:
   virtuoso-bridge start

4. Load daemon SKILL in Virtuoso CIW (once per Virtuoso session):
   load("/tmp/virtuoso_bridge_<user>/virtuoso_bridge/virtuoso_setup.il")

5. Verify:
   virtuoso-bridge status
   python3 scripts/check_virtuoso_connection.py

6. T28 .env only needs:
   CDS_LIB_PATH_28=/path/to/cds.lib
   # AMS_OUTPUT_ROOT (optional)
```

---

## 7. Summary: What virtuoso-bridge-lite Replaces

| Removed from T28 | Replaced by |
|---|---|
| `ramic_bridge.il` (SKILL server) | `virtuoso-bridge-lite/core/ramic_bridge.il` |
| `ramic_bridge.py` (Python TCP client) | `VirtuosoClient.execute_skill()` |
| `ramic_bridge_daemon_27.py` | VB's own daemon (deployed by `virtuoso-bridge start`) |
| `_import_rbexc()` | `_get_client()` |
| `use_ramic_bridge()` | (removed — always uses VB) |
| skillbridge `else` branches | (removed) |
| `csh("...")` SKILL hack for Calibre | `SSHClient.upload_file()` + `run_command()` |
| `rb_exec('load("path")')` — no upload | `VirtuosoClient.load_il(path)` — SSH upload |
