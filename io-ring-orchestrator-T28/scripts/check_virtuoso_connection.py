#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Check Virtuoso Connection - T28 Skill Script

Enhanced version with full diagnostic capability from old version.
Checks if Virtuoso is running and accessible via RAMIC Bridge or skillbridge.
Provides detailed troubleshooting information.

Usage:
    python check_virtuoso_connection.py

Exit Codes:
    0 - Virtuoso is connected
    1 - Virtuoso not connected or error
    2 - Import/setup error
"""

import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# Add assets to path for local imports
skill_dir = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(skill_dir))

# Load skill-local .env so checks don't depend on caller's cwd.
env_file = skill_dir / ".env"
if env_file.exists():
    load_dotenv(dotenv_path=env_file, override=False)
else:
    load_dotenv(override=False)


def check_via_ramic_bridge() -> tuple[bool, list]:
    """
    Check Virtuoso connection via RAMIC Bridge.

    Returns:
        (success, report_lines) tuple
    """
    report = []
    report.append("Bridge Type: RAMIC Bridge")
    report.append("")

    try:
        from assets.utils.bridge_utils import rb_exec

        # Test with expected result validation
        test_command = "(1+1)"
        result = rb_exec(test_command, timeout=5)

        report.append(f"Test Command: {test_command}")
        report.append(f"Response: {result}")
        report.append("")

        # Validate expected result (should be "2")
        if result == "2":
            report.append("✅ Virtuoso Connection: OK")
            report.append("• Bridge responded with correct result (2)")
            return True, report
        else:
            report.append("⚠️  Virtuoso Connection: UNCERTAIN")
            report.append(f"• Bridge responded: {result}")
            report.append("• Expected: 2")
            report.append("• Connection may be working but response format unexpected")
            return False, report

    except ImportError as e:
        report.append(f"Error: {type(e).__name__}: {e}")
        report.append("")
        report.append("❌ Virtuoso Connection: FAILED")
        report.append("Check if RAMIC Bridge daemon is running")
        report.append("• Ensure USE_RAMIC_BRIDGE=true is set")
        return False, report
    except Exception as e:
        report.append(f"Error: {str(e)}")
        report.append("")
        report.append("❌ Virtuoso Connection: FAILED")
        report.append("Check if RAMIC Bridge daemon is running")
        return False, report


def check_via_skillbridge() -> tuple[bool, list]:
    """
    Check Virtuoso connection via skillbridge.

    Returns:
        (success, report_lines) tuple
    """
    report = []
    report.append("Bridge Type: skillbridge")
    report.append("")

    try:
        import skillbridge

        report.append("Attempting to connect to Virtuoso...")
        report.append("")

        # Try to open workspace
        ws = skillbridge.Workspace.open()

        if ws is None:
            report.append("❌ Virtuoso Connection: FAILED")
            report.append("• Could not open Virtuoso workspace")
            report.append("• Ensure Virtuoso is running")
            report.append("• Ensure skillbridge daemon is running")
            return False, report

        # Test command
        test_command = "(1+1)"
        report.append(f"Test Command: {test_command}")

        try:
            result = ws.eval(test_command)

            report.append(f"Response: {result}")
            report.append("")

            if result == 2:
                report.append("✅ Virtuoso Connection: OK")
                report.append("• skillbridge responded with correct result (2)")
                return True, report
            else:
                report.append("⚠️  Virtuoso Connection: UNCERTAIN")
                report.append(f"• skillbridge responded: {result}")
                report.append("• Expected: 2")
                return False, report

        except skillbridge.Error as e:
            report.append(f"Error executing command: {str(e)}")
            report.append("")
            report.append("❌ Virtuoso Connection: FAILED")
            return False, report

    except ImportError as e:
        report.append(f"Error: {type(e).__name__}: {e}")
        report.append("")
        report.append("❌ Virtuoso Connection: FAILED")
        report.append("• skillbridge module not available")
        report.append("• Try setting USE_RAMIC_BRIDGE=true to use RAMIC Bridge")
        return False, report
    except Exception as e:
        report.append(f"Error: {type(e).__name__}: {e}")
        report.append("")
        report.append("❌ Virtuoso Connection: FAILED")
        return False, report


def check_environment() -> list:
    """
    Check environment variables for Virtuoso connection.

    Returns:
        List of environment status messages
    """
    report = []
    report.append("")
    report.append("=== Environment Check ===")
    report.append("")

    # Check USE_RAMIC_BRIDGE
    use_ramic = os.getenv("USE_RAMIC_BRIDGE", "false").lower() in ["true", "1", "yes"]
    report.append(f"USE_RAMIC_BRIDGE: {os.getenv('USE_RAMIC_BRIDGE', 'not set')}")
    report.append(f"  → Using RAMIC Bridge: {use_ramic}")
    report.append("")

    # Check RB_HOST
    rb_host = os.getenv("RB_HOST", "not set")
    report.append(f"RB_HOST: {rb_host}")
    if rb_host == "not set":
        report.append("  → ⚠️  Not configured (required for RAMIC Bridge)")
    report.append("")

    # Check RB_PORT
    rb_port = os.getenv("RB_PORT", "not set")
    report.append(f"RB_PORT: {rb_port}")
    if rb_port == "not set":
        report.append("  → ⚠️  Not configured (required for RAMIC Bridge)")
    report.append("")

    return report


def print_troubleshooting(bridge_type: str, success: bool):
    """
    Print troubleshooting hints based on test results.
    """
    print("")
    print("=== Troubleshooting ===")
    print("")

    if not success:
        if bridge_type == "ramic":
            print("If RAMIC Bridge connection failed:")
            print("  1. Check if RAMIC Bridge daemon is running:")
            print("     ps aux | grep ramic_bridge")
            print("  2. Check RB_HOST and RB_PORT environment variables")
            print("  3. Check RAMIC Bridge logs for errors")
            print("  4. Ensure Virtuoso CIW is running")
            print("  5. Try restarting RAMIC Bridge daemon")
            print("")
            print("To switch to skillbridge instead:")
            print("  export USE_RAMIC_BRIDGE=false")
            print("  python check_virtuoso_connection.py")
        else:
            print("If skillbridge connection failed:")
            print("  1. Check if Virtuoso is running:")
            print("     ps aux | grep virtuoso")
            print("  2. Check if skillbridge daemon is running:")
            print("     ps aux | grep skillbridge")
            print("  3. Try restarting skillbridge daemon")
            print("  4. Check Virtuoso CIW is accepting connections")
            print("  5. Ensure no firewall is blocking the connection")
            print("")
            print("To switch to RAMIC Bridge instead:")
            print("  export USE_RAMIC_BRIDGE=true")
            print("  export RB_HOST=<your_host>")
            print("  export RB_PORT=<your_port>")
            print("  python check_virtuoso_connection.py")
    else:
        print("✅ Virtuoso connection is working!")
        print("If you still experience issues with tools:")
        print("  1. Check tool timeout settings")
        print("  2. Verify library/cell/view names are correct")
        print("  3. Check Virtuoso memory/CPU usage")
        print("  4. Review Virtuoso log files for errors")


def main():
    """Main entry point with full diagnostics."""
    print("🔧 Virtuoso Connection Check - Enhanced Diagnostics")
    print("=" * 60)
    print()

    # Determine which bridge to use
    use_ramic = os.getenv("USE_RAMIC_BRIDGE", "false").lower() in ["true", "1", "yes"]

    # Check environment first
    env_report = check_environment()
    for line in env_report:
        print(line)

    # Run appropriate test
    if use_ramic:
        success, report = check_via_ramic_bridge()
    else:
        success, report = check_via_skillbridge()

    # Print test report
    print("")
    print("=== Test Report ===")
    for line in report:
        print(line)

    # Print troubleshooting hints
    bridge_type = "ramic" if use_ramic else "skillbridge"
    print_troubleshooting(bridge_type, success)

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
