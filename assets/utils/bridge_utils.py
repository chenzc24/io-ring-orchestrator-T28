from __future__ import annotations

from typing import Optional, Tuple
import os
import json
import sys

from dotenv import load_dotenv


def _load_skill_env() -> None:
    """Load .env from skill root (deterministic, independent of cwd)."""
    skill_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    env_file = os.path.join(skill_root, ".env")
    if os.path.exists(env_file):
        load_dotenv(dotenv_path=env_file, override=False)
    else:
        # Fallback to default search behavior for compatibility.
        load_dotenv(override=False)


_load_skill_env()

# Add external_scripts to sys.path for importing bundled ramic_bridge
_external_scripts_path = os.path.join(os.path.dirname(__file__), '..', 'external_scripts')
if _external_scripts_path not in sys.path:
    sys.path.insert(0, _external_scripts_path)


def use_ramic_bridge() -> bool:
    """
    Decide whether to use ramic_bridge based on environment variable.
    Returns True when USE_RAMIC_BRIDGE is one of {"1","true","yes"} (case-insensitive).
    """
    return os.getenv("USE_RAMIC_BRIDGE", "").strip().lower() in {"1", "true", "yes"}


def _import_rbexc():
    """
    Import RBExc from the skill's bundled ramic_bridge.
    """
    try:
        from ramic_bridge.ramic_bridge import RBExc  # type: ignore
        return RBExc
    except Exception as e:
        raise ImportError(
            f"Could not import RBExc from {_external_scripts_path}. "
            f"Please ensure ramic_bridge is available in assets/external_scripts/. Error: {e}"
        )


def rb_exec(skill: str, timeout: int = 30, host: Optional[str] = None, port: Optional[int] = None) -> str:
    """
    Execute SKILL code via ramic_bridge.

    Honors RB_HOST/RB_PORT from environment, or use provided host/port parameters.
    Defaults to 127.0.0.1:65432. Cleans control characters from return.

    Args:
        skill: SKILL code to execute
        timeout: Timeout in seconds
        host: Optional host override (if None, uses RB_HOST env var)
        port: Optional port override (if None, uses RB_PORT env var)
    """
    RBExc = _import_rbexc()
    rb_host = host if host is not None else os.getenv("RB_HOST", "127.0.0.1")
    if port is not None:
        rb_port = port
    else:
        try:
            rb_port = int(os.getenv("RB_PORT", "65432"))
        except Exception:
            rb_port = 65432
    try:
        ret = RBExc(skill, host=rb_host, port=rb_port, timeout=timeout) or ""
        # Remove protocol control chars (STX/NAK/RS) and other non-printables
        cleaned = "".join(ch for ch in str(ret) if ord(ch) >= 32).strip()
        return cleaned
    except json.JSONDecodeError as e:
        # If JSON parsing fails in bridge communication, raise it so caller can handle
        raise
    except Exception as e:
        # For other exceptions, return error message as string
        return f"Bridge execution error: {str(e)}"


def get_current_design() -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Get (lib, cell, view) for current edit cellView using either ramic_bridge or skillbridge.
    Returns (None, None, None) if not available.
    """
    if use_ramic_bridge():
        try:
            skill_code = 'sprintf(nil "%s" ddGetObjReadPath(dbGetCellViewDdId(geGetEditCellView())))'
            ret = rb_exec(skill_code, timeout=30)
            if not ret:
                return None, None, None
            parts = ret.split('/')
            if len(parts) < 4:
                return None, None, None
            return parts[-4], parts[-3], parts[-2]
        except Exception:
            return None, None, None
    else:
        try:
            from skillbridge import Workspace  # type: ignore
            ws = Workspace.open()
            try:
                cv = ws['geGetEditCellView']()
                if not cv:
                    return None, None, None
                ddId = ws['dbGetCellViewDdId'](cv)
                full_path = ws['ddGetObjReadPath'](ddId)
                parts = str(full_path).split('/')
                if len(parts) < 4:
                    return None, None, None
                return parts[-4], parts[-3], parts[-2]
            finally:
                ws.close()
        except Exception:
            return None, None, None



# ===================== High-level helpers =====================
def _escape_path_for_skill(path: str) -> str:
    """
    Escape path for SKILL string literal.
    """
    return path.replace("\\", "\\\\").replace('"', '\\"')


def load_skill_file(file_path: str, timeout: int = 60) -> bool:
    """
    Load a .il/.skill file in Virtuoso via active bridge.
    Returns True on success, False otherwise.
    """
    abs_path = _escape_path_for_skill(file_path)
    if use_ramic_bridge():
        ret = rb_exec(f'load("{abs_path}")', timeout=timeout)
        # load returns t on success; rb_exec stringifies: check empty as success fallback
        return ret == '' or ret.lower() in {'t', 't\n'}
    else:
        try:
            from skillbridge import Workspace  # type: ignore
            ws = Workspace.open()
            try:
                ws['load'](file_path)
                return True
            finally:
                ws.close()
        except Exception:
            return False


def save_current_cellview(timeout: int = 30) -> bool:
    """
    Save current edit cellView. Returns True on success.
    """
    if use_ramic_bridge():
        ret = rb_exec('dbSave(cv)', timeout=timeout)
        # RAMIC bridge commonly returns 't' for success; older versions may return 'OK'.
        cleaned = (ret or '').strip().lower()
        return cleaned == 't' or 'ok' in cleaned
    else:
        try:
            from skillbridge import Workspace  # type: ignore
            ws = Workspace.open()
            try:
                cv = ws['geGetEditCellView']()
                ws['dbSave'](cv)
                return True
            finally:
                ws.close()
        except Exception:
            return False


def ui_redraw(timeout: int = 10) -> None:
    if use_ramic_bridge():
        rb_exec('hiRedraw()', timeout=timeout)
    else:
        try:
            from skillbridge import Workspace  # type: ignore
            ws = Workspace.open()
            try:
                ws['hiRedraw']()
            finally:
                ws.close()
        except Exception:
            pass


def ui_zoom_absolute_scale(scale: float, timeout: int = 10) -> None:
    if use_ramic_bridge():
        rb_exec(f'hiZoomAbsoluteScale(geGetEditCellViewWindow(cv) {scale})', timeout=timeout)
    else:
        try:
            from skillbridge import Workspace  # type: ignore
            ws = Workspace.open()
            try:
                win = ws['hiGetCurrentWindow']()
                ws['hiZoomAbsoluteScale'](win, scale)
            finally:
                ws.close()
        except Exception:
            pass


def _default_view_type_for(view: str) -> str:
    """
    Map logical view to viewType used by dbOpenCellViewByType.
    e.g. layout -> maskLayout, schematic -> schematic.
    """
    v = (view or "").strip().lower()
    # Treat any view starting with "layout" as maskLayout (e.g., layout, layout1, layout_top)
    if v.startswith("layout"):
        return "maskLayout"
    if v == "schematic":
        return "schematic"
    # fallback: use same as view
    return view


def open_cell_view_by_type(
    lib: str,
    cell: str,
    view: str = "layout",
    view_type: Optional[str] = None,
    mode: str = "w",
    timeout: int = 30,
) -> bool:
    """
    Open a specific cellView in Virtuoso using dbOpenCellViewByType and optionally set it as current edit view.

    Args:
        lib: Library name
        cell: Cell name
        view: View name (e.g. "layout" | "schematic")
        view_type: View type (default deduced: layout->maskLayout, schematic->schematic)
        mode: Open mode (e.g. "r" | "w")
        timeout: Bridge call timeout seconds

    Returns:
        True if opened successfully, False otherwise
    """
    if not view_type:
        view_type = _default_view_type_for(view)
    if use_ramic_bridge():
        # Build SKILL snippet
        lib_s = lib.replace('"', '\\"')
        cell_s = cell.replace('"', '\\"')
        view_s = view.replace('"', '\\"')
        vtype_s = (view_type or "").replace('"', '\\"')
        mode_s = (mode or "w").replace('"', '\\"')
        # Only open and return cv (no side effects like setting edit view)
        skill = (
            f'cv = dbOpenCellViewByType("{lib_s}" "{cell_s}" "{view_s}" "{vtype_s}" "{mode_s}")'
        )
        try:
            ret = rb_exec(skill, timeout=timeout)
            # If cv is nil, return will likely contain "nil"; success returns a db object printed string
            cleaned = (ret or "").strip().lower()
            return cleaned != "nil" and len(cleaned) > 0
        except Exception:
            return False
    else:
        try:
            from skillbridge import Workspace  # type: ignore
            ws = Workspace.open()
            try:
                cv = ws['dbOpenCellViewByType'](lib, cell, view, view_type, mode)
                if not cv:
                    return False
                return True
            finally:
                ws.close()
        except Exception:
            return False


def ge_open_window(
    lib: str,
    cell: str,
    view: str = "layout",
    view_type: Optional[str] = None,
    mode: str = "a",
    timeout: int = 30,
) -> bool:
    """
    Open a window in Virtuoso using geOpen to display cellView.

    Args:
        lib: Library name
        cell: Cell name
        view: View name (e.g. "layout" | "schematic")
        view_type: View type (default deduced: layout->maskLayout, schematic->schematic)
        mode: Open mode (default: "a" for append)
        timeout: Bridge call timeout seconds

    Returns:
        True if window opened successfully, False otherwise
    """
    if not view_type:
        view_type = _default_view_type_for(view)
    if use_ramic_bridge():
        # Build SKILL snippet with named parameters
        lib_s = lib.replace('"', '\\"')
        cell_s = cell.replace('"', '\\"')
        view_s = view.replace('"', '\\"')
        vtype_s = (view_type or "").replace('"', '\\"')
        mode_s = (mode or "a").replace('"', '\\"')
        # Use geOpen with named parameters
        skill = (
            f'window = geOpen(?lib "{lib_s}" ?cell "{cell_s}" ?view "{view_s}" ?viewType "{vtype_s}" ?mode "{mode_s}")'
        )
        try:
            ret = rb_exec(skill, timeout=timeout)
            # Check if window was opened successfully (geOpen returns window object or nil)
            cleaned = (ret or "").strip().lower()
            return cleaned != "nil" and len(cleaned) > 0
        except Exception:
            return False
    else:
        try:
            from skillbridge import Workspace  # type: ignore
            ws = Workspace.open()
            try:
                window = ws['geOpen'](lib=lib, cell=cell, view=view, viewType=view_type, mode=mode)
                if not window:
                    return False
                return True
            finally:
                ws.close()
        except Exception:
            return False


def open_cell_view(
    lib: str,
    cell: str,
    view: str = "layout",
    timeout: int = 30,
) -> bool:
    """
    Open a specific cellView in Virtuoso using dbOpenCellViewByType and optionally set it as current edit view.

    Args:
        lib: Library name
        cell: Cell name
        view: View name (e.g. "layout" | "schematic")
        timeout: Bridge call timeout seconds

    Returns:
        True if opened successfully, False otherwise
    """
    if use_ramic_bridge():
        # Build SKILL snippet
        lib_s = lib.replace('"', '\\"')
        cell_s = cell.replace('"', '\\"')
        view_s = view.replace('"', '\\"')
        # Only open and return cv (no side effects like setting edit view)
        skill = (
            f'cv = dbOpenCellView("{lib_s}" "{cell_s}" "{view_s}")'
        )
        try:
            ret = rb_exec(skill, timeout=timeout)
            # If cv is nil, return will likely contain "nil"; success returns a db object printed string
            cleaned = (ret or "").strip().lower()
            return cleaned != "nil" and len(cleaned) > 0
        except Exception:
            return False
    else:
        try:
            from skillbridge import Workspace  # type: ignore
            ws = Workspace.open()
            try:
                cv = ws['dbOpenCellView'](lib, cell, view)
                if not cv:
                    return False
                return True
            finally:
                ws.close()
        except Exception:
            return False


def load_script_and_take_screenshot_verbose(screenshot_script_path: str, save_path: str, timeout: int = 20) -> tuple[bool, str]:
    """
    Load a screenshot SKILL script and take screenshot to save_path.
    Returns (success, error_message). error_message is empty on success.
    """
    scr = _escape_path_for_skill(screenshot_script_path)
    out = _escape_path_for_skill(save_path)
    if use_ramic_bridge():
        # Load screenshot script; success is empty or 't'
        load_ret = rb_exec(f'load("{scr}")', timeout=timeout)
        if not (load_ret == '' or load_ret.strip().lower() in {'t', 't\n'}):
            return False, f"load failed: {load_ret}"
        # Invoke takeScreenshot; treat any non-empty error-ish output as failure
        take_ret = rb_exec(f'takeScreenshot("{out}")', timeout=timeout)
        if take_ret and ('error' in take_ret.lower() or 'undefined function' in take_ret.lower()):
            return False, f"takeScreenshot failed: {take_ret}"
        # Verify that file was actually created
        if not os.path.exists(save_path):
            return False, "screenshot file not created"
        return True, ""
    else:
        try:
            from skillbridge import Workspace  # type: ignore
            ws = Workspace.open()
            try:
                ws['load'](screenshot_script_path)
                ws['takeScreenshot'](save_path)
                if not os.path.exists(save_path):
                    return False, "screenshot file not created"
                return True, ""
            finally:
                ws.close()
        except Exception as e:
            return False, f"exception: {e}"


def load_script_and_take_screenshot(screenshot_script_path: str, save_path: str, timeout: int = 20) -> bool:
    """
    Backward-compatible wrapper returning only success flag.
    """
    ok, _ = load_script_and_take_screenshot_verbose(screenshot_script_path, save_path, timeout=timeout)
    return ok


def execute_csh_script(script_path: str, *args, timeout: int = 300) -> str:
    """
    Execute a csh script either remotely via ramic_bridge or locally via subprocess.
    
    Args:
        script_path: Path to the csh script
        *args: Arguments to pass to the script
        timeout: Timeout in seconds (default: 300)
    
    Returns:
        String result of the script execution
    """
    # Convert to absolute path
    abs_script_path = os.path.abspath(script_path)
    
    def _run_local_csh() -> str:
        try:
            import subprocess

            cmd = ["/bin/csh", abs_script_path] + [str(arg) for arg in args]
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8:replace"

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            stdout, stderr = process.communicate(timeout=timeout)

            if process.returncode == 0:
                return stdout or "t"
            return f"Local csh execution failed: {stderr or stdout}"
        except Exception as e:
            return f"Local csh execution failed: {e}"

    def _escape_for_skill_csh(text: str) -> str:
        """Escape text for embedding inside SKILL csh("...") string."""
        return str(text).replace("\\", "\\\\").replace('"', '\\"')

    if use_ramic_bridge():
        # Remote execution via ramic_bridge
        print(f"Remote execution via ramic_bridge")
        try:
            # Build command string for csh execution
            # In SKILL, csh() executes a command and returns "t" on success or "nil" on failure
            # Execute script from project root directory to ensure relative paths work correctly
            project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
            script_rel_path = os.path.relpath(abs_script_path, project_root)
            cmd_tokens = []
            for arg in args:
                escaped_arg = _escape_for_skill_csh(str(arg))
                if any(ch.isspace() for ch in str(arg)):
                    cmd_tokens.append(f'\\"{escaped_arg}\\"')
                else:
                    cmd_tokens.append(escaped_arg)
            cmd_args = " ".join(cmd_tokens)
            ams_output_root = os.environ.get("AMS_OUTPUT_ROOT", "").strip()
            ams_output_root_escaped = _escape_for_skill_csh(ams_output_root) if ams_output_root else ""
            project_root_escaped = _escape_for_skill_csh(project_root)
            script_rel_path_escaped = _escape_for_skill_csh(script_rel_path)
            
            # Change to project root directory, then execute script with arguments
            # Use && to chain commands: cd to project root && execute script
            if ams_output_root_escaped:
                script_cmd = (
                    f'csh("cd {project_root_escaped}; '
                    f'setenv AMS_OUTPUT_ROOT {ams_output_root_escaped}; '
                    f'./{script_rel_path_escaped} {cmd_args}")'
                )
            else:
                script_cmd = f'csh("cd {project_root_escaped}; ./{script_rel_path_escaped} {cmd_args}")'
            
            # Get connection parameters from environment
            rb_host = os.getenv("RB_HOST", "127.0.0.1")
            try:
                rb_port = int(os.getenv("RB_PORT", "65432"))
            except Exception:
                rb_port = 65432
            
            RBExc = _import_rbexc()
            result = RBExc(script_cmd, rb_host, rb_port, timeout=timeout)
            
            # Clean control characters and check for success
            # In SKILL, csh() returns "t" on success, "nil" on failure
            # The result may contain control characters: STX (0x02) for success, NAK (0x15) for error
            if result:
                # Remove control characters (STX, NAK, RS, etc.) and whitespace
                cleaned_result = "".join(ch for ch in result if ord(ch) >= 32).strip()
                
                # Check for "nil" - this means csh() failed in SKILL
                if cleaned_result.lower() == "nil":
                    local_result = _run_local_csh()
                    if not str(local_result).startswith("Local csh execution failed"):
                        return local_result
                    return f"Remote csh execution failed: SKILL csh() returned nil. This usually means:\n" \
                           f"  1. Script file not found or not executable\n" \
                           f"  2. Script execution failed (check script permissions and content)\n" \
                           f"  3. Script path or arguments are incorrect\n" \
                           f"  Command: {script_cmd}\n" \
                           f"  Fallback local execution: {local_result}"
                
                # Check if result ends with "t" (success indicator from SKILL csh())
                if cleaned_result.lower().endswith("t") or cleaned_result.lower() == "t":
                    # Success - return the result (may contain script output)
                    return result
                elif cleaned_result.lower() in ["none", ""]:
                    local_result = _run_local_csh()
                    if not str(local_result).startswith("Local csh execution failed"):
                        return local_result
                    return f"Remote csh execution failed: empty result; fallback local execution: {local_result}"
                elif "error" in cleaned_result.lower() or "failed" in cleaned_result.lower() or cleaned_result.lower().startswith("usage:"):
                    # Contains error keywords, treat as failure
                    return f"Remote csh execution failed: {cleaned_result}"
                else:
                    # Non-empty result that doesn't end with "t" and doesn't contain error keywords
                    # This might be script output. In SKILL, csh() returns "t" on success,
                    # but if the script outputs text, it might be mixed.
                    # We'll check if it looks like an error or just output
                    # For now, if it doesn't look like an error, treat as success with output
                    # The caller can check the actual script output files to verify
                    return result
            else:
                local_result = _run_local_csh()
                if not str(local_result).startswith("Local csh execution failed"):
                    return local_result
                print("Failure: result is empty or None")
                return f"Remote csh execution failed: {result or 'nil/empty result'}; fallback local execution: {local_result}"
        except Exception as e:
            local_result = _run_local_csh()
            if not str(local_result).startswith("Local csh execution failed"):
                return local_result
            return f"Remote csh execution failed: {str(e)}; fallback local execution: {local_result}"
    else:
        # Local execution via subprocess
        return _run_local_csh()

