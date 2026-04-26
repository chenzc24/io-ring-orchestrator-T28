#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Intent Graph Validator - Validates T28 intent graph files
"""

import re
import sys
import json
from pathlib import Path
from typing import Dict, Any

def validate_config(config: Dict[str, Any]) -> bool:
    """Validate configuration completeness"""
    if not config:
        print("[ERROR] Error: Configuration is empty")
        return False

    # Validate ring_config
    if 'ring_config' not in config:
        print("[ERROR] Error: Missing ring_config field")
        return False

    ring_config = config['ring_config']

    # Validate width and height
    if 'width' not in ring_config:
        print("[ERROR] Error: ring_config missing width field")
        return False

    if 'height' not in ring_config:
        print("[ERROR] Error: ring_config missing height field")
        return False

    def _as_count(value, default=0):
        """Best-effort normalize count-like values to int."""
        if value is None:
            return default
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default

    width = _as_count(ring_config.get('width', 0))
    height = _as_count(ring_config.get('height', 0))

    if width <= 0 or height <= 0:
        print("[ERROR] Error: width and height must be positive")
        return False

    expected_counts = {
        'left': height,
        'right': height,
        'top': width,
        'bottom': width,
    }

    # Validate placement_order
    if 'placement_order' not in ring_config:
        print("[ERROR] Error: ring_config missing placement_order field")
        return False

    placement_order = ring_config['placement_order']
    if placement_order not in ['clockwise', 'counterclockwise']:
        print("[ERROR] Error: placement_order must be 'clockwise' or 'counterclockwise'")
        return False

    # Validate instances
    if 'instances' not in config:
        print("[ERROR] Error: Missing instances field")
        return False

    instances = config['instances']
    if not instances or not isinstance(instances, list):
        print("[ERROR] Error: instances must be a non-empty list")
        return False

    # Validate basic fields for each instance
    corner_positions = set()
    position_counts = {'left': 0, 'right': 0, 'top': 0, 'bottom': 0}

    for i, instance in enumerate(instances):
        if not isinstance(instance, dict):
            print(f"[ERROR] Error: instance[{i}] must be a dictionary")
            return False

        # Validate required fields
        if 'name' not in instance:
            print(f"[ERROR] Error: instance[{i}] missing name field")
            return False

        # Support both "device" and "device_type" for backward compatibility
        device = instance.get("device") or instance.get("device_type", "")
        if not device:
            print(f"[ERROR] Error: instance[{i}] missing device or device_type field")
            return False

        if 'position' not in instance:
            print(f"[ERROR] Error: instance[{i}] missing position field")
            return False

        name = instance['name']
        device = instance.get("device") or instance.get("device_type", "")
        position = instance['position']

        # Validate corner device name: check for duplicate _G suffix (before other validations)
        if position.startswith(('top_left', 'top_right', 'bottom_left', 'bottom_right')):
            # This is a corner position, validate device name
            if device.endswith("_G_G"):
                print(f"[ERROR] Error: instance[{i}] {name}'s corner device has duplicate _G suffix: '{device}'. Should be '{device[:-2]}' (only one _G suffix allowed)")
                return False

        # Validate device suffix rules
        if not validate_device_suffix(device, position):
            print(f"[ERROR] Error: instance[{i}] {name}'s device suffix doesn't match position")
            return False

        # Validate position format
        if not validate_position_format(position, width, height, expected_counts):
            print(f"[ERROR] Error: instance[{i}] {name}'s position format is incorrect")
            return False

        # Count positions and corner points (only count outer ring pads, exclude inner ring pads)
        if position.startswith(('top_left', 'top_right', 'bottom_left', 'bottom_right')):
            corner_positions.add(position)
        else:
            # Only count outer ring pads, don't count inner ring pads
            instance_type = instance.get('type', 'pad')
            if instance_type != 'inner_pad':  # Exclude inner ring pads
                for side in ['left', 'right', 'top', 'bottom']:
                    if position.startswith(side + '_'):
                        position_counts[side] += 1
                        break

        # Validate type field (if exists)
        if 'type' in instance:
            instance_type = instance['type']
            valid_types = ['filler', 'pad', 'inner_pad', 'corner']
            if instance_type not in valid_types:
                print(f"[ERROR] Error: instance[{i}] {name}'s type field value is incorrect: got '{instance_type}', expected one of {valid_types}")
                return False

            # Validate corner type
            if instance_type == 'corner':
                if not position.startswith(('top_left', 'top_right', 'bottom_left', 'bottom_right')):
                    print(f"[ERROR] Error: instance[{i}] {name}'s corner type position format is incorrect")
                    return False
                
                # Validate corner device name: check for duplicate _G suffix
                if device not in ["PCORNER_G", "PCORNERA_G"]:
                    print(f"[ERROR] Error: instance[{i}] {name}'s corner device name is incorrect: got '{device}', expected 'PCORNER_G' or 'PCORNERA_G'")
                    return False

        # Validate direction field (required for digital IO; PDDW16SDGZ default, PRUW08SDGZ alternative)
        if device.startswith('PDDW16SDGZ') or device.startswith('PRUW08SDGZ'):
            if 'direction' not in instance:
                print(f"[ERROR] Error: instance[{i}] {name}'s digital IO missing direction field")
                return False
            direction = instance['direction']
            if direction not in ['input', 'output']:
                print(f"[ERROR] Error: instance[{i}] {name}'s direction must be 'input' or 'output'")
                return False

        # Validate pin_connection (if exists)
        if 'pin_connection' in instance:
            pin_connection = instance['pin_connection']
            if not isinstance(pin_connection, dict):
                print(f"[ERROR] Error: instance[{i}] {name}'s pin_connection must be a dictionary")
                return False

            # Validate digital IO pin_connection (both PDDW16SDGZ and PRUW08SDGZ share identical VDD/VSS/VDDPST/VSSPST requirements)
            if device.startswith('PDDW16SDGZ') or device.startswith('PRUW08SDGZ'):
                required_pins = ['VDD', 'VSS', 'VDDPST', 'VSSPST']
                for pin in required_pins:
                    if pin not in pin_connection:
                        print(f"[ERROR] Error: instance[{i}] {name}'s digital IO missing {pin} pin configuration")
                        return False

            # Validate analog device VSS pin
            if device.startswith(('PDB3AC', 'PVDD', 'PVSS')):
                if 'VSS' not in pin_connection:
                    print(f"[ERROR] Error: instance[{i}] {name}'s analog device missing VSS pin configuration")
                    return False

    # Validate corner count
    if len(corner_positions) != 4:
        print(f"[ERROR] Error: Incorrect corner count, expected 4, actual {len(corner_positions)}")
        return False

    # Validate pad count for each side independently
    expected_left = expected_counts['left']
    expected_right = expected_counts['right']
    expected_top = expected_counts['top']
    expected_bottom = expected_counts['bottom']

    if position_counts['left'] != expected_left:
        print(f"[ERROR] Error: Left side pad count incorrect, expected {expected_left}, actual {position_counts['left']}")
        return False

    if position_counts['right'] != expected_right:
        print(f"[ERROR] Error: Right side pad count incorrect, expected {expected_right}, actual {position_counts['right']}")
        return False

    if position_counts['top'] != expected_top:
        print(f"[ERROR] Error: Top side pad count incorrect, expected {expected_top}, actual {position_counts['top']}")
        return False

    if position_counts['bottom'] != expected_bottom:
        print(f"[ERROR] Error: Bottom side pad count incorrect, expected {expected_bottom}, actual {position_counts['bottom']}")
        return False

    # Validation passed, display statistics
    print(f"[STATS] Validation statistics:")
    print(f"  - IO ring scale: {width} x {height}")
    print(f"  - Corner count: {len(corner_positions)}")
    print(f"  - Left side pad count: {position_counts['left']}")
    print(f"  - Right side pad count: {position_counts['right']}")
    print(f"  - Top side pad count: {position_counts['top']}")
    print(f"  - Bottom side pad count: {position_counts['bottom']}")
    print(f"  - Total outer ring pads: {sum(position_counts.values())}")
    print(f"  - Total instances: {len(instances)}")

    # Count device types
    device_types = {}
    for instance in instances:
        device = instance.get('device', 'unknown')
        device_types[device] = device_types.get(device, 0) + 1

    print(f"  - Device type statistics:")
    for device, count in sorted(device_types.items()):
        print(f"    * {device}: {count}")

    print("[OK] Configuration validation passed")
    return True

def validate_device_suffix(device: str, position: str) -> bool:
    """Validate device suffix compatibility with position for T28

    T28 devices must have suffix (_H_G or _V_G) matching position
    Corner devices don't need suffix validation, only position validation
    """
    # Corner validation: only need to judge if position is a legal corner position
    if position.startswith(('top_left', 'top_right', 'bottom_left', 'bottom_right')):
        return True

    # Left and right side pads must use _H_G suffix
    if position.startswith(('left_', 'right_')):
        if not device.endswith('_H_G'):
            return False

    # Top and bottom side pads must use _V_G suffix
    elif position.startswith(('top_', 'bottom_')):
        if not device.endswith('_V_G'):
            return False

    return True

def validate_position_format(position: str, width: int, height: int, side_limits: Dict[str, int] = None) -> bool:
    """Validate position format correctness"""
    if side_limits is None:
        side_limits = {
            'left': height,
            'right': height,
            'top': width,
            'bottom': width,
        }

    # Corner positions
    if position in ['top_left', 'top_right', 'bottom_left', 'bottom_right']:
        return True

    # Outer ring pad positions
    pattern = r'^(left|right|top|bottom)_(\d+)$'
    match = re.match(pattern, position)
    if match:
        side = match.group(1)
        index = int(match.group(2))

        limit = side_limits.get(side)
        if not isinstance(limit, int) or limit <= 0:
            return False
        return 0 <= index < limit

    # Inner ring pad positions
    pattern = r'^(left|right|top|bottom)_(\d+)_(\d+)$'
    match = re.match(pattern, position)
    if match:
        side = match.group(1)
        index1 = int(match.group(2))
        index2 = int(match.group(3))

        limit = side_limits.get(side)
        if not isinstance(limit, int) or limit <= 0:
            return False
        return 0 <= index1 < limit and 0 <= index2 < limit and index1 != index2

    return False

def convert_config_to_list(config: Dict[str, Any]) -> list:
    """Convert intent graph to list format required by generator

    Normalizes field names to standard format
    """
    config_list = []

    # Add ring_config
    if 'ring_config' in config:
        ring_config = config['ring_config'].copy()
        ring_config['type'] = 'ring_config'
        config_list.append(ring_config)

    # Add instances
    if 'instances' in config:
        for instance in config['instances']:
            instance_config = instance.copy()

            # Normalize field names: support both device/device_type
            if 'device_type' in instance_config and 'device' not in instance_config:
                instance_config['device'] = instance_config.pop('device_type')

            # Keep original type field, don't override
            if 'type' not in instance_config:
                instance_config['type'] = 'instance'
            config_list.append(instance_config)

    return config_list

def get_config_statistics(config: Dict[str, Any]) -> Dict[str, Any]:
    """Get configuration statistics"""
    ring_config = config.get('ring_config', {})
    instances = config.get('instances', [])

    # Count different types of devices
    device_types = {}
    for instance in instances:
        device = instance.get('device', 'unknown')
        device_types[device] = device_types.get(device, 0) + 1

    # Count digital IO inputs/outputs (both device types)
    digital_ios = [inst for inst in instances if inst.get('device') in ('PDDW16SDGZ', 'PRUW08SDGZ')]
    input_ios = [io for io in digital_ios if io.get('direction') == 'input']
    output_ios = [io for io in digital_ios if io.get('direction') == 'output']

    return {
        'ring_size': f"{ring_config.get('width', 'N/A')} x {ring_config.get('height', 'N/A')}",
        'total_pads': len(instances),
        'device_types': len(device_types),
        'digital_ios': len(digital_ios),
        'input_ios': len(input_ios),
        'output_ios': len(output_ios)
    }

def main():
    """Main entry point for standalone CLI usage"""

    if len(sys.argv) < 2:
        print("Usage: python validate_intent.py <config_file_path>")
        print("\nValidates T28 IO Ring intent graph JSON files.")
        print("\nExit codes:")
        print("  0 - Validation passed")
        print("  1 - Validation failed")
        print("  2 - File or JSON error")
        sys.exit(2)

    config_file_path = sys.argv[1]
    config_path = Path(config_file_path)

    # Check file exists
    if not config_path.exists():
        print(f"[ERROR] Error: File not found: {config_file_path}")
        sys.exit(2)

    # Load JSON
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        print(f"[ERROR] Error: Invalid JSON format")
        print(f"   {e}")
        sys.exit(2)
    except Exception as e:
        print(f"[ERROR] Error: Failed to load file")
        print(f"   {e}")
        sys.exit(2)

    # Validate
    is_valid = validate_config(config)

    if is_valid:
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
