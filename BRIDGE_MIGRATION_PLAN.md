# Bridge Migration Plan — io-ring-orchestrator-T28 → virtuoso-bridge-lite

> **Status:** For review — no files have been changed yet.  
> **Principle:** All RAMIC-bridge code is removed from T28. Every bridging function
> is re-implemented by calling `VirtuosoClient` from `virtuoso-bridge-lite`.
> Connection configuration moves entirely to `~/.virtuoso-bridge/.env`,
> managed by the `virtuoso-bridge` CLI. `virtuoso-bridge-lite` is **not touched**.

---

## 1. What Changes and Why

| Before | After |
|---|---|
| T28 bundles its own RAMIC bridge (3 Python/SKILL files) | Those files are deleted |
| `bridge_utils.py` imports `ramic_bridge.py` from `assets/external_scripts/` | Imports `VirtuosoClient` from `virtuoso_bridge` package |
| Connection config (`RB_HOST`, `RB_PORT`, `USE_RAMIC_BRIDGE`) lives in T28's `.env` | Connection config lives in `~/.virtuoso-bridge/.env`, managed by `virtuoso-bridge init` |
| `check_virtuoso_connection.py` tests the bundled bridge | Tests via `VirtuosoClient.from_env()` |
| README tells users to load T28's `ramic_bridge.il` in Virtuoso CIW | README tells users to install virtuoso-bridge-lite and run `virtuoso-bridge start` |

---

## 2. Files to DELETE

```
assets/external_scripts/ramic_bridge/ramic_bridge.il
assets/external_scripts/ramic_bridge/ramic_bridge.py
assets/external_scripts/ramic_bridge/ramic_bridge_daemon_27.py
```

The `assets/external_scripts/ramic_bridge/` directory is gone after deletion.

---

## 3. `assets/utils/bridge_utils.py`

### 3.1 Remove entirely

| Item | What it is |
|---|---|
| `sys.path` block (lines 24–27) | Added `external_scripts/` to import path for bundled bridge |
| `use_ramic_bridge()` | Read `USE_RAMIC_BRIDGE` env flag — flag no longer exists |
| `_import_rbexc()` | Imported `RBExc` from the now-deleted `ramic_bridge.py` |
| All `else: skillbridge...` branches | Every `if use_ramic_bridge(): ... else: skillbridge...` block — remove the `else` branch |

---

### 3.2 New private helper `_get_client()`

This is the single point that creates a `VirtuosoClient`.  
It pre-loads `~/.virtuoso-bridge/.env` **before** calling `from_env()`, so that
VirtuosoClient always finds its connection config even when scripts run from inside
the T28 skill directory (where T28's own `.env` would otherwise be picked up first).

```python
def _get_client():
    try:
        from virtuoso_bridge import VirtuosoClient  # type: ignore
    except ImportError:
        raise ImportError(
            "virtuoso-bridge is not installed.\n"
            "See README.md > Prerequisites:\n"
            "  pip install -e /path/to/virtuoso-bridge-lite"
        )
    # Pre-load VB's standard env before from_env() re-reads the nearest .env.
    # Prevents T28's skill-root .env from shadowing VB connection variables.
    from pathlib import Path
    _vb_env = Path.home() / ".virtuoso-bridge" / ".env"
    if _vb_env.is_file():
        from dotenv import load_dotenv
        load_dotenv(_vb_env, override=True)

    return VirtuosoClient.from_env()
```

`VirtuosoClient.from_env()` (virtuoso-bridge-lite public API):
- If `virtuoso-bridge start` tunnel is active → connects to its local port.
- If no tunnel → reads `VB_REMOTE_HOST` from env and starts one automatically.
- Returns a ready-to-use `VirtuosoClient`.

---

### 3.3 `rb_exec()` — rewrite

`rb_exec` is kept as the internal workhorse so all other functions need no changes
beyond the removal of the `if use_ramic_bridge():` guards.

**Before:**
```python
def rb_exec(skill: str, timeout: int = 30, host=None, port=None) -> str:
    RBExc = _import_rbexc()
    rb_host = host if host is not None else os.getenv("RB_HOST", "127.0.0.1")
    rb_port = port if port is not None else int(os.getenv("RB_PORT", "65432"))
    ret = RBExc(skill, host=rb_host, port=rb_port, timeout=timeout) or ""
    cleaned = "".join(ch for ch in str(ret) if ord(ch) >= 32).strip()
    return cleaned
```

**After:**
```python
def rb_exec(skill: str, timeout: int = 30) -> str:
    """Execute SKILL code via virtuoso-bridge-lite."""
    try:
        result = _get_client().execute_skill(skill, timeout=timeout)
        return result.output or ""
    except json.JSONDecodeError:
        raise
    except Exception as e:
        return f"Bridge execution error: {str(e)}"
```

Key differences:
| | Before | After |
|---|---|---|
| Transport | `ramic_bridge.RBExc()` → raw TCP bytes | `VirtuosoClient.execute_skill()` → `VirtuosoResult` |
| Control-char strip | `"".join(ch for ch in ret if ord(ch) >= 32)` — manual | Not needed — `VirtuosoResult.output` is already clean |
| `host` / `port` params | Passed through to `RBExc` | **Removed** — connection is fully managed by VirtuosoClient |
| Return type | `str` | `str` (unchanged) |

`VirtuosoResult.output` — the field used:
```python
class VirtuosoResult(BaseModel):
    status: ExecutionStatus   # SUCCESS / FAILURE / PARTIAL / ERROR
    output: str = ""          # ← this is what we return; already clean string
    errors: list[str] = []
    ok: bool                  # property: status == SUCCESS
    is_nil: bool              # property: output is "nil" or ""
```

---

### 3.4 `get_current_design()` — simplify

Remove `if use_ramic_bridge():` guard and the entire skillbridge `else` branch.
Keep only the SKILL-execution body:

```python
def get_current_design() -> Tuple[Optional[str], Optional[str], Optional[str]]:
    try:
        ret = rb_exec(
            'sprintf(nil "%s" ddGetObjReadPath(dbGetCellViewDdId(geGetEditCellView())))',
            timeout=30,
        )
        if not ret:
            return None, None, None
        parts = ret.split('/')
        if len(parts) < 4:
            return None, None, None
        return parts[-4], parts[-3], parts[-2]
    except Exception:
        return None, None, None
```

---

### 3.5 `load_skill_file()` — rewrite with `client.load_il()`

**Why not `rb_exec('load("...")')`?**  
A raw SKILL `load("/local/path")` call tells Virtuoso to read a file from **its own
server filesystem**. If the `.il` file only exists locally, Virtuoso cannot find it.

`VirtuosoClient.load_il(path)` checks `_tunnel is not None`; when an SSH tunnel is
active it uploads the local file to the remote server via SCP before calling
`load()` in Virtuoso CIW. This is the correct behaviour for SSH-based remote setups.

```python
def load_skill_file(file_path: str, timeout: int = 60) -> bool:
    result = _get_client().load_il(file_path, timeout=timeout)
    return result.ok
```

**Flow:**
1. `_get_client()` → `VirtuosoClient.from_env()` (with SSH tunnel)
2. `load_il(path)` → `_prepare_il_path()`:
   - If tunnel active and file exists locally → upload via SSH → return remote path
   - If no tunnel (local Virtuoso) → use local path as-is
3. Executes `load("/remote/tmp/vb/filename.il")` SKILL in Virtuoso CIW

---

### 3.6 `save_current_cellview()` — simplify

```python
def save_current_cellview(timeout: int = 30) -> bool:
    ret = rb_exec('dbSave(cv)', timeout=timeout)
    cleaned = (ret or '').strip().lower()
    return cleaned == 't' or 'ok' in cleaned
```

---

### 3.7 `ui_redraw()` — simplify

```python
def ui_redraw(timeout: int = 10) -> None:
    rb_exec('hiRedraw()', timeout=timeout)
```

---

### 3.8 `ui_zoom_absolute_scale()` — simplify

```python
def ui_zoom_absolute_scale(scale: float, timeout: int = 10) -> None:
    rb_exec(f'hiZoomAbsoluteScale(geGetEditCellViewWindow(cv) {scale})', timeout=timeout)
```

---

### 3.9 `open_cell_view_by_type()` — simplify

Remove `if use_ramic_bridge():` guard; keep the SKILL-snippet body unchanged.
Remove the `else: skillbridge...` block.

```python
def open_cell_view_by_type(lib, cell, view="layout", view_type=None, mode="w", timeout=30) -> bool:
    if not view_type:
        view_type = _default_view_type_for(view)
    lib_s   = lib.replace('"', '\\"')
    cell_s  = cell.replace('"', '\\"')
    view_s  = view.replace('"', '\\"')
    vtype_s = (view_type or "").replace('"', '\\"')
    mode_s  = (mode or "w").replace('"', '\\"')
    skill = (
        f'cv = dbOpenCellViewByType("{lib_s}" "{cell_s}" "{view_s}" "{vtype_s}" "{mode_s}")'
    )
    try:
        ret = rb_exec(skill, timeout=timeout)
        cleaned = (ret or "").strip().lower()
        return cleaned != "nil" and len(cleaned) > 0
    except Exception:
        return False
```

---

### 3.10 `ge_open_window()` — simplify

Same pattern as 3.9. Remove `if/else`, keep SKILL snippet.

---

### 3.11 `open_cell_view()` — simplify

Same pattern as 3.9.

---

### 3.12 `load_script_and_take_screenshot_verbose()` — rewrite with `client.load_il()`

The `screenshot.il` SKILL file also needs to be uploaded to the remote server before
it can be loaded in Virtuoso CIW. Same reasoning as `load_skill_file()`.

`takeScreenshot()` writes the PNG to a path on the **Virtuoso server's** filesystem.
If the server and local machine share a filesystem (NFS), `save_path` works as-is.
Without NFS a `client.download_file()` step would be needed to pull the PNG back —
this is unchanged from the original design (the original RAMIC bridge had the same
limitation).

```python
def load_script_and_take_screenshot_verbose(
    screenshot_script_path: str, save_path: str, timeout: int = 20
) -> tuple[bool, str]:
    client = _get_client()
    out = _escape_path_for_skill(save_path)

    # Upload screenshot.il to server (if SSH tunnel active), then load in CIW
    load_result = client.load_il(screenshot_script_path, timeout=timeout)
    if not load_result.ok:
        return False, f"load failed: {'; '.join(load_result.errors) or 'unknown error'}"

    # Execute takeScreenshot — save_path is resolved on the Virtuoso server
    take_ret = rb_exec(f'takeScreenshot("{out}")', timeout=timeout)
    if take_ret and ('error' in take_ret.lower() or 'undefined function' in take_ret.lower()):
        return False, f"takeScreenshot failed: {take_ret}"

    if not os.path.exists(save_path):
        return False, "screenshot file not created"
    return True, ""
```

---

### 3.13 `load_script_and_take_screenshot()` — unchanged

Wrapper that calls `load_script_and_take_screenshot_verbose`. No changes.

---

### 3.14 `execute_csh_script()` — full rewrite via `SSHClient`

**Why not `rb_exec('csh("...")')`?**  
The old approach routed calibre execution through Virtuoso's SKILL `csh()` interpreter,
which added unnecessary overhead, fragile output parsing (STX/NAK/control chars), and
required the calibre script directory to pre-exist on the Virtuoso server. With
`virtuoso-bridge-lite`'s `SSHClient`, we can upload the scripts and run them directly
over SSH — cleaner, reliable stdout/stderr, and no Virtuoso involvement for calibre.

**Capabilities used (public `SSHClient` API):**

```python
from virtuoso_bridge import SSHClient

ssh = SSHClient.from_env()
ssh.upload_file(local_path, remote_path)   # upload via tar pipe
ssh.run_command(cmd, timeout)              # execute on server, return CommandResult
ssh.download_file(remote_path, local_path) # retrieve a file from server
```

`CommandResult` fields: `returncode: int`, `stdout: str`, `stderr: str`

**After — complete replacement of `execute_csh_script()`:**

```python
def execute_csh_script(script_path: str, *args, timeout: int = 300) -> str:
    """Upload calibre csh script to server and run it directly via SSH."""
    import shlex
    from pathlib import Path
    from dotenv import load_dotenv

    script = Path(script_path).resolve()
    if not script.exists():
        return f"Script not found: {script}"

    try:
        from virtuoso_bridge import SSHClient  # type: ignore
    except ImportError:
        raise ImportError(
            "virtuoso-bridge is not installed. "
            "See README.md > Prerequisites for installation instructions."
        )

    # Pre-load VB env (same pattern as _get_client)
    _vb_env = Path.home() / ".virtuoso-bridge" / ".env"
    if _vb_env.is_file():
        load_dotenv(_vb_env, override=True)

    ssh = SSHClient.from_env()

    # Upload the entire calibre directory to a stable remote temp location.
    # This is idempotent — subsequent runs overwrite the same remote paths.
    calibre_dir = script.parent
    remote_base = "/tmp/vb_t28_calibre"

    for f in calibre_dir.rglob("*"):
        if f.is_file():
            rel = f.relative_to(calibre_dir).as_posix()
            up = ssh.upload_file(f, f"{remote_base}/{rel}", timeout=60)
            if up.returncode != 0:
                return f"Upload failed ({f.name}): {up.stderr.strip()}"

    # Build and execute the remote command
    remote_script = f"{remote_base}/{script.relative_to(calibre_dir).as_posix()}"
    args_str = " ".join(shlex.quote(str(a)) for a in args)
    ams_root = os.environ.get("AMS_OUTPUT_ROOT", "").strip()
    env_prefix = f"AMS_OUTPUT_ROOT={shlex.quote(ams_root)} " if ams_root else ""

    result = ssh.run_command(
        f"chmod +x {shlex.quote(remote_script)} && "
        f"{env_prefix}csh {shlex.quote(remote_script)} {args_str}",
        timeout=timeout,
    )

    if result.returncode == 0:
        return result.stdout or "t"
    return (
        f"Remote execution failed (rc={result.returncode}):\n"
        f"{result.stderr or result.stdout}"
    )
```

**What this gives you vs the old SKILL `csh()` approach:**

| | Old: `rb_exec('csh("...")')` | New: `SSHClient.run_command()` |
|---|---|---|
| Transport | TCP → Virtuoso daemon → SKILL `csh()` | Direct SSH |
| Output | Parsed SKILL return string ("t"/"nil") | Raw stdout + stderr |
| Return code | Inferred from SKILL string | Actual process exit code |
| Script upload | Not handled (must pre-exist on server) | Always uploaded fresh |
| Control-char stripping | Required | Not needed |
| Virtuoso must be running | Yes | No |

---

### 3.15 Helpers — unchanged

| Function | Reason |
|---|---|
| `_load_skill_env()` | Loads T28's own `.env` for `CDS_LIB_PATH_28`, output paths — independent of bridge |
| `_escape_path_for_skill()` | Pure string helper |
| `_default_view_type_for()` | Pure string helper |

---

## 4. `scripts/check_virtuoso_connection.py`

### 4.1 `check_via_ramic_bridge()` → replaced by `check_via_virtuoso_bridge()`

```python
def check_via_virtuoso_bridge() -> tuple[bool, list]:
    report = ["Bridge Type: virtuoso-bridge-lite", ""]

    try:
        from virtuoso_bridge import VirtuosoClient  # type: ignore
    except ImportError:
        report += ["❌ virtuoso-bridge not installed", "• See README.md > Prerequisites"]
        return False, report

    try:
        from pathlib import Path
        from dotenv import load_dotenv
        _vb_env = Path.home() / ".virtuoso-bridge" / ".env"
        if _vb_env.is_file():
            load_dotenv(_vb_env, override=True)

        client = VirtuosoClient.from_env()
        result = client.execute_skill("(1+1)", timeout=5)

        report.append(f"Test Command: (1+1)")
        report.append(f"Response: {result.output!r}  (ok={result.ok})")
        report.append("")

        if result.ok and result.output.strip() == "2":
            report += ["✅ Virtuoso Connection: OK", "• Bridge responded with correct result (2)"]
            return True, report

        report += [
            "⚠️  Virtuoso Connection: UNCERTAIN",
            f"• Bridge responded: {result.output!r}",
            "• Expected: '2'",
        ]
        return False, report

    except Exception as e:
        report += [f"Error: {e}", "", "❌ Virtuoso Connection: FAILED",
                   "• Run: virtuoso-bridge status"]
        return False, report
```

### 4.2 `check_via_skillbridge()` — delete entirely

### 4.3 `check_environment()` — rewrite

Remove `USE_RAMIC_BRIDGE`, `RB_HOST`, `RB_PORT` checks.
Show virtuoso-bridge-lite status instead:

```python
def check_environment() -> list:
    report = ["", "=== Environment Check ===", ""]
    try:
        import virtuoso_bridge
        report.append(f"virtuoso-bridge version: {virtuoso_bridge.__version__}")
    except ImportError:
        report.append("virtuoso-bridge: NOT INSTALLED")
    report.append("")
    report.append("Run 'virtuoso-bridge status' to check tunnel and daemon state.")
    return report
```

### 4.4 `print_troubleshooting()` — rewrite

```
If connection failed:
  1. Check virtuoso-bridge status:
       virtuoso-bridge status
  2. Start or restart the tunnel:
       virtuoso-bridge start
       virtuoso-bridge restart
  3. Confirm the daemon SKILL file is loaded in Virtuoso CIW:
       load("/path/to/virtuoso-bridge-lite/core/ramic_bridge.il")
  4. Check ~/.virtuoso-bridge/.env has correct VB_REMOTE_HOST / VB_LOCAL_PORT
```

### 4.5 `main()` — update

```python
# BEFORE:
use_ramic = os.getenv("USE_RAMIC_BRIDGE", "false").lower() in ["true", "1", "yes"]
if use_ramic:
    success, report = check_via_ramic_bridge()
else:
    success, report = check_via_skillbridge()
bridge_type = "ramic" if use_ramic else "skillbridge"

# AFTER:
success, report = check_via_virtuoso_bridge()
bridge_type = "virtuoso-bridge-lite"
```

---

## 5. `.env` — rewrite

Remove all bridge connection vars. T28's `.env` becomes purely about the T28
toolchain (CDS paths, output paths). Virtuoso connection is configured in
`~/.virtuoso-bridge/.env`.

```env
# T28 IO Ring Orchestrator — toolchain configuration
# Bridge connection is managed by virtuoso-bridge-lite.
# Configure it once with: virtuoso-bridge init && virtuoso-bridge start
# See README.md > Prerequisites.

# Path to your T28 cds.lib (used by Calibre strmout/si wrappers)
CDS_LIB_PATH_28=/home/chenzc_intern25/TSMC28/llm_IO/cds.lib

# Optional output path controls (see README for resolution order)
#AMS_OUTPUT_ROOT=/absolute/path/to/workspace/output
#AMS_IO_AGENT_PATH=/absolute/path/to/workspace
```

**Removed vars:**

| Var | Reason removed |
|---|---|
| `USE_RAMIC_BRIDGE` | Bridge is always used; flag has no meaning anymore |
| `RB_HOST` | Connection host managed by `~/.virtuoso-bridge/.env` |
| `RB_PORT` | Connection port managed by `~/.virtuoso-bridge/.env` |

---

## 6. `requirements.txt` — update

```text
# Python runtime dependencies for T28 IO Ring Orchestrator
# Python 3.9+

# === Prerequisite — install BEFORE this skill ===
# virtuoso-bridge-lite provides VirtuosoClient (the Virtuoso bridge).
# It is not on PyPI; install from its source directory:
#
#   pip install -e /path/to/virtuoso-bridge-lite
#
# Minimum required version: 0.6.0
# After installing, run:  virtuoso-bridge init && virtuoso-bridge start
# See README.md > Prerequisites for full setup instructions.

python-dotenv>=1.0,<2.0
matplotlib>=3.5,<4.0
```

---

## 7. `README.md` — structural changes

### Overview paragraph

Remove "self-contained" / "no separate package installation is needed."
Replace with:

> Relies on **virtuoso-bridge-lite** for all Virtuoso communication. Install that first
> (see Prerequisites).

### Prerequisites table — add row

| `virtuoso-bridge-lite ≥ 0.6` | **Required.** Provides `VirtuosoClient`, the TCP daemon, and SSH tunnel management. |

### Installation — new Step 0 (before everything else)

```markdown
### 0. Install virtuoso-bridge-lite (once per machine)

```bash
git clone <virtuoso-bridge-lite repo>
cd virtuoso-bridge-lite
pip install -e .

# Configure connection (edit the generated file with your server details)
virtuoso-bridge init          # creates ~/.virtuoso-bridge/.env
virtuoso-bridge start         # starts SSH tunnel + deploys daemon
virtuoso-bridge status        # verify: tunnel ✓  daemon ✓
```

Load the daemon SKILL file in Virtuoso CIW (once per Virtuoso session):
```skill
load("/tmp/virtuoso_bridge_<user>/virtuoso_bridge/virtuoso_setup.il")
```
> `virtuoso-bridge start` prints the exact path to load.
```

### Step 4 (was: "Start the RAMIC Bridge") — replace

```markdown
### 4. Start the Virtuoso bridge

```bash
virtuoso-bridge start
```

The bridge is now managed by virtuoso-bridge-lite. All connection details
(host, port, SSH) are in `~/.virtuoso-bridge/.env`.
```

### Configuration section

- Remove the `USE_RAMIC_BRIDGE`, `RB_HOST`, `RB_PORT` rows from the variable table.
- Update the `.env` code block to match the cleaned file.
- Add a note: "For Virtuoso connection settings, see `~/.virtuoso-bridge/.env`
  (created by `virtuoso-bridge init`)."

### File Structure — update `assets/external_scripts/` block

Remove the `ramic_bridge/` subtree listing.

### Troubleshooting — replace RAMIC bridge section

```markdown
**Virtuoso connection fails:**
- Run `virtuoso-bridge status` to check tunnel and daemon state
- Run `virtuoso-bridge restart` to force-restart
- Confirm daemon SKILL file is loaded in Virtuoso CIW
- See `virtuoso-bridge-lite/README.md` for detailed troubleshooting
```

### Related Documentation table — update

Replace `ramic_bridge/README.md` row:

| virtuoso-bridge-lite | `virtuoso-bridge-lite/README.md` | Full bridge setup: SSH tunnels, daemon, multi-profile, CLI reference |

---

## 8. End-to-End Execution Flow After Migration

### `run_il_with_screenshot.py`

```
[Claude Code / User]
    │
    ▼
run_il_with_screenshot.py::run_il_file()
    │
    ├─ open_cell_view_by_type()  → rb_exec('dbOpenCellViewByType(...)')
    │      TCP → Virtuoso daemon → SKILL executed on server ✓
    │
    ├─ ge_open_window()          → rb_exec('geOpen(...)')
    │      TCP → Virtuoso daemon → SKILL executed on server ✓
    │
    ├─ rb_exec('cv = geGetEditCellView()')
    │      TCP → Virtuoso daemon → SKILL executed on server ✓
    │
    └─ load_skill_file(layout.il)
           │
           └─ client.load_il("/local/path/io_ring_layout.il")
                  │
                  ├─ SSH upload → /tmp/vb_<user>/io_ring_layout.il  (on server)
                  │
                  └─ rb_exec('load("/tmp/vb_<user>/io_ring_layout.il")')
                         TCP → Virtuoso daemon → SKILL loads .il on server ✓
                         IO Ring schematic/layout created in Virtuoso ✓

    ▼
load_script_and_take_screenshot()
    │
    ├─ client.load_il("screenshot.il")
    │      SSH upload → /tmp/vb_<user>/screenshot.il  (on server)
    │      rb_exec('load(...)') → defines takeScreenshot() in Virtuoso ✓
    │
    └─ rb_exec('takeScreenshot("/path/screenshot.png")')
           Virtuoso writes PNG to server filesystem ✓
           (retrieved locally via NFS or separate download step)
```

### `run_drc.py` / `run_lvs.py`

```
run_drc.py
    │
    └─ execute_csh_script("run_drc.csh", lib, cell, ...)
           │
           ├─ SSHClient.from_env()  (SSH tunnel already running)
           │
           ├─ ssh.upload_file(env_common.csh  → /tmp/vb_t28_calibre/env_common.csh)
           ├─ ssh.upload_file(run_drc.csh     → /tmp/vb_t28_calibre/run_drc.csh)
           ├─ ssh.upload_file(T28/rules...    → /tmp/vb_t28_calibre/T28/...)
           │      All uploaded via tar pipe over SSH ✓
           │
           └─ ssh.run_command("csh /tmp/vb_t28_calibre/run_drc.csh lib cell")
                  Executes directly on server (no Virtuoso needed) ✓
                  Calibre DRC runs on server ✓
                  Returns CommandResult(returncode, stdout, stderr) ✓
                  Python receives actual exit code + full output ✓
```

**This is strictly better than the old approach:**
- No SKILL `csh()` indirection through Virtuoso
- Real exit code instead of "t"/"nil" string parsing
- Full stdout + stderr instead of truncated SKILL return
- Scripts always uploaded fresh — no manual server-side setup needed

---

## 9. Backward-Compatibility Notes

| Component | Change | User impact |
|---|---|---|
| `rb_exec()` signature | `host`/`port` params removed | No callers pass them explicitly → no impact |
| `.env` bridge vars | `USE_RAMIC_BRIDGE`, `RB_HOST`, `RB_PORT` removed | Users must migrate to `~/.virtuoso-bridge/.env` |
| Virtuoso CIW load path | Points to `virtuoso-bridge-lite/core/ramic_bridge.il` | User reloads SKILL file once |
| SKILL return strings | Same format; no behaviour change | None |

---

## 9. Handling Future virtuoso-bridge-lite Updates

- Only stable public API is used: `VirtuosoClient`, `from_env()`, `execute_skill()`,
  `test_connection()` — all declared in `VirtuosoInterface` (abstract base).
- The `ImportError` guard in `_get_client()` prints an actionable install hint if the
  package is missing or renamed.
- The `~/.virtuoso-bridge/.env` pre-load uses only `python-dotenv` (already a T28
  dependency) — no coupling to VB internals.
- Minimum version `0.6.0` is documented in `requirements.txt`.

---

## 10. Verification Steps

```bash
# 1. Bundled bridge is gone
ls io-ring-orchestrator-T28/assets/external_scripts/ramic_bridge/
# → No such file or directory

# 2. No remaining references to bundled bridge or old env vars
grep -rn "ramic_bridge.py\|_import_rbexc\|use_ramic_bridge\|RB_HOST\|RB_PORT\|USE_RAMIC_BRIDGE" \
    io-ring-orchestrator-T28/assets/utils/bridge_utils.py \
    io-ring-orchestrator-T28/scripts/check_virtuoso_connection.py \
    io-ring-orchestrator-T28/.env
# → 0 matches

# 3. Import sanity (no Virtuoso needed)
python -c "from assets.utils.bridge_utils import rb_exec, open_cell_view_by_type; print('OK')"

# 4. Connection test (Virtuoso + virtuoso-bridge running)
virtuoso-bridge status
python3 scripts/check_virtuoso_connection.py
# → ✅ Virtuoso Connection: OK
```
