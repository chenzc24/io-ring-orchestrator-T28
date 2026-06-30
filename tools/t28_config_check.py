#!/usr/bin/env python3
"""Validate the unified T28 IO Ring _local/site.yaml configuration."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools.t28_site_config import apply_site_config
from tools.t28_site_config import site as site_mod


def _load_generator_device_masters() -> dict[str, str]:
    config_path = (
        REPO_ROOT
        / "skills"
        / "t28-ioring-generator"
        / "io_ring"
        / "layout"
        / "config"
        / "lydevices_28.json"
    )
    defaults = {"default_library": "tphn28hpcpgv18", "pad_library": "PAD"}
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return defaults

    masters = data.get("device_masters", {})
    if not isinstance(masters, dict):
        return defaults

    merged = defaults.copy()
    for key, value in masters.items():
        if isinstance(value, str) and value.strip():
            merged[key] = value.strip()
    return merged


def _print_site_specific_reminders() -> None:
    masters = _load_generator_device_masters()
    required_libs = sorted(
        {
            masters.get("default_library", "").strip(),
            masters.get("pad_library", "").strip(),
        }
        - {""}
    )
    pad_masters = [
        masters.get("pad60_master", "").strip(),
        masters.get("pad60nu_master", "").strip(),
    ]
    pad_masters = [name for name in pad_masters if name]

    print("Site-specific PDK/PAD reminders:")
    print("  Confirm DRC rule deck: skills/t28-ioring-generator/calibre/T28/_drc_rule_T28_cell_")
    print("  Confirm LVS rule deck: skills/t28-ioring-generator/calibre/T28/_calibre_T28.lvs_")
    print("  Confirm PEX rule deck: skills/t28-ioring-generator/calibre/T28/_calibre_T28.rcx_")
    print("  Confirm calibre.pdk_layermap_28 and calibre.lvs_include_28 match your PDK.")
    if required_libs:
        print("  Confirm cadence.cds_lib_28 DEFINEs libraries: " + ", ".join(required_libs))
    if pad_masters:
        print("  Physical PAD masters expected in PAD library: " + ", ".join(pad_masters))


def main() -> int:
    path = site_mod.site_config_path(REPO_ROOT)
    errors = site_mod.validate_site_config(REPO_ROOT)
    if errors:
        print("[ERROR] T28 site configuration is not ready.")
        print(f"Config path: {path}")
        for err in errors:
            print(f"  - {err}")
        return 1

    apply_site_config(REPO_ROOT)
    print("[OK] T28 site configuration is ready.")
    print(f"Config path: {path}")
    for name in (
        "AMS_OUTPUT_ROOT",
        "AMS_DRAFT_EDITOR",
        "AMS_LAYOUT_EDITOR",
        "VB_FS_MODE",
        "VB_DISABLE_CONTROL_MASTER",
        "CDS_LIB_PATH_28",
        "SIM_CDS_LIB",
        "SIM_IC_ROOT",
        "SIM_MMSIM_ROOT",
        "MGC_HOME",
        "PDK_LAYERMAP_28",
        "incFILE_28",
        "SIM_PDK_IO_SPECTRE_INCLUDE",
        "SIM_PDK_CORE_SPECTRE_INCLUDE",
        "SIM_PDK_CORE_SPECTRE_SECTIONS",
        "SIM_LM_LICENSE_FILE",
        "SIM_CDS_LIC_FILE",
    ):
        value = site_mod.read_config_value(name, REPO_ROOT)
        redacted = "<set>" if ("LICENSE" in name or "LIC_FILE" in name) and value else value
        print(f"  {name}={redacted}")
    _print_site_specific_reminders()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
