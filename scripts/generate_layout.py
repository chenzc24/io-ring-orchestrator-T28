#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate Layout - T28 Skill Script

Generates layout SKILL (.il) code from confirmed config JSON.
Uses local imports from assets/core/.

Usage:
    python generate_layout.py <config.json> <output.il>

Exit Codes:
    0 - Success
    1 - Tool execution error
    2 - Import/setup error
"""

import json
import os
import sys
from pathlib import Path

# Add assets to path for local imports
skill_dir = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(skill_dir))


def _resolve_output_root() -> Path:
    """Resolve unified output root for generated reports/artifacts.

    Priority:
    1) AMS_OUTPUT_ROOT env var (explicit override)
    2) AMS_IO_AGENT_PATH/output (workspace root hint)
    3) Current working directory output
    4) Legacy skill-relative output
    """
    env_root = os.environ.get("AMS_OUTPUT_ROOT", "").strip()
    if env_root:
        return Path(env_root).expanduser().resolve(strict=False)

    agent_root = os.environ.get("AMS_IO_AGENT_PATH", "").strip()
    if agent_root:
        return (Path(agent_root).expanduser().resolve(strict=False) / "output")

    cwd_output = Path(os.getcwd()) / "output"
    return cwd_output.resolve(strict=False)


def _resolve_confirmed_config_path(config_path: Path, consume_confirmed_only: bool) -> Path:
    """Resolve confirmed config path with auto-build logic."""
    if not consume_confirmed_only:
        return config_path

    if config_path.name.endswith("_confirmed.json"):
        return config_path

    expected_confirmed = config_path.with_name(f"{config_path.stem}_confirmed.json")
    if expected_confirmed.exists():
        return expected_confirmed

    # Build confirmed config if not exists
    from assets.core.layout.confirmed_config_builder import (
        build_confirmed_config_from_io_config as build_confirmed_t28,
    )

    generated = Path(build_confirmed_t28(str(config_path)))
    if generated.exists():
        return generated

    raise ValueError(
        "Editor-confirmed config required. "
        f"Expected: {expected_confirmed}. "
        "Please run build_io_ring_confirmed_config first."
    )


def main():
    from assets.core.layout.layout_visualizer import visualize_layout
    from assets.core.layout.layout_generator_factory import generate_layout_from_json
    from assets.core.intent_graph.json_validator import convert_config_to_list

    assets_dir = skill_dir / "assets"

    # Parse arguments
    if len(sys.argv) < 3:
        print("Usage: python generate_layout.py <config.json> <output.il>")
        print("\nArguments:")
        print("  config.json  - Path to confirmed config file")
        print("  output.il    - Path for output layout SKILL file")
        print("\nExample:")
        print("  python generate_layout.py io_ring_confirmed.json layout.il")
        sys.exit(2)

    config_path = sys.argv[1]
    output_path = sys.argv[2]

    # Check input file exists
    if not Path(config_path).exists():
        print(f"[ERROR] Error: Input file not found: {config_path}")
        sys.exit(2)

    try:
        print(f"[>>] Generating layout SKILL code...")
        print(f"   Input:  {config_path}")
        print(f"   Output: {output_path}")

        config_path_obj = Path(config_path)

        # Resolve confirmed config path (auto-build if needed)
        config_path = _resolve_confirmed_config_path(config_path_obj, consume_confirmed_only=True)

        # Ensure output path is .il
        output_path_obj = Path(output_path)
        output_path_obj.parent.mkdir(parents=True, exist_ok=True)
        if output_path_obj.suffix.lower() != ".il":
            output_path_obj = output_path_obj.with_suffix(".il")

        # Load and convert config
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        config_list = convert_config_to_list(config)

        # Generate layout
        generate_layout_from_json(str(config_path), str(output_path_obj), "T28")

        # Generate visualization (matches original logic)
        vis_path = output_path_obj.parent / f"{output_path_obj.stem}_visualization.png"
        try:
            visualize_layout(str(output_path_obj), str(vis_path))
            vis_generated = True
        except Exception:
            vis_generated = False

        if vis_generated and Path(vis_path).exists():
            print(f"\n[OK] Successfully generated layout file: {output_path_obj}")
            print(f"[STATS] Layout visualization generated: {vis_path}")
            print("[TIP] Tip: Review visualization image to verify layout arrangement.")
        else:
            print(f"\n[OK] Successfully generated layout file: {output_path_obj}")

        sys.exit(0)

    except Exception as e:
        print(f"[ERROR] Error during layout generation: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
