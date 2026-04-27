# Enrichment Engine Plan — v2 (Robust)

> Hybrid AI+code architecture for T28 IO Ring enrichment.
> AI owns semantic decisions. Code owns mechanical execution.
> v2 incorporates self-review fixes: wiring corrections, missing gates, rollback strategy, semantic intent contract details, realistic implementation scope.

---

## Changelog from v1

| Issue in v1 | Fix in v2 |
|-------------|-----------|
| Bug: `PVSS1AC.TACVSS` and `PVSS1A.TAVSS` set to `self` instead of `domain.vss_provider` | Wiring table corrected; load-time validator added |
| Missing domain continuity gate | Added gate G8 |
| Redundant `role` field | Dropped; device name is single source of truth |
| Pin override semantics underspecified | Defined: literal-only by default, optional `label_from:` prefix for references |
| No rollback plan | `AMS_USE_ENGINE` flag + side-by-side comparison mode for first 2 weeks |
| Inner pad position validation absent | Engine validates index1<index2 and side-range at input |
| Wizard integration unclear | Explicit: wizard runs before semantic intent generation |
| Wiring table correctness assumed | Pre-implementation: domain expert review + cross-check against `IO_device_info_T28.json` |
| 30 goldens lack semantic_intent files | Phase 0 added: generate semantic intents from goldens before engine work |
| SKILL.md change underestimated | Treated as 4-hour prompt engineering task, not docs update |
| Provider count = 4 too rigid | Loosened: "exactly 4 unique names IF design has digital signals" |
| Engine output format implicit | Field-by-field schema spec |
| No structured logging | JSON trace log alongside intent_graph output |
| No engine unit tests | Test plan in §13 |
| Optimistic 3-day timeline | Realistic 7-10 day timeline with parallelizable phases |

---

## 1. Problem Statement

Steps 2-5 of the T28 pipeline are entirely AI-driven: Claude reads ~700 lines of enrichment rules, reasons in natural language about every signal's device, pins, and corners, then generates JSON. Failure modes:

| Problem | Root cause |
|---------|-----------|
| Hallucinated pin labels | AI must remember suffix rules, `_CORE` rules, domain provider names per pin per device |
| Repair loops in Step 4-5 | Exist only to catch AI mechanical mistakes |
| Token burn | ~17K tokens of enrichment rules consumed every run |

Some decisions genuinely require AI judgment — device choice (PVDD3AC vs PVDD3A), domain grouping, direction inference. These cannot be codified without losing generality.

## 2. The Split

```
AI OWNS (semantic — needs design judgment, project-specific)
══════════════════════════════════════════════════════════════
  signal class      analog_io / digital_io / analog_power_provider / ...
  device choice     PDB3AC vs PDB4BC, PVDD3AC vs PVDD3A
  domain grouping   which signals share a voltage domain
  provider names    which signals are VDD/VSS providers per domain
  direction         input vs output (digital IO)
  ring ESD          whether ring-wide ESD is active, signal name

CODE OWNS (mechanical — fixed by PDK, zero judgment)
══════════════════════════════════════════════════════════════
  suffix            left/right → _H_G, top/bottom → _V_G
  pin wiring        every pin on every device, wired to correct domain signal
  _CORE suffix      AVDD/AVSS on provider devices → {name}_CORE
  IO direction pins REN/OEN/C/I behavior (input vs output, PDDW16 vs PRUW08)
  corners           check 2 adjacent pad devices → PCORNER_G or PCORNERA_G
  gate checks       continuity, provider count, VSS consistency, domain continuity
  ring ESD override every pad's VSS → ESD signal name when active
```

The device name is the handoff point. AI says *which* device. Code says *how* it's wired.

## 3. What This Plan Does NOT Eliminate

The engine reduces **mechanical** errors, not **semantic** errors. If the AI assigns a digital signal to an analog domain, the engine will produce a syntactically valid intent graph that passes `validate_intent.py` but is still semantically wrong — DRC/LVS in Steps 11-12 remain the ultimate correctness check. This plan should improve first-pass DRC/LVS rates significantly but will not eliminate DRC/LVS failures entirely.

## 4. Data Flow

```
OLD:
  user prompt → AI reads enrichment_rules → AI generates full intent_graph (~200 lines)
              → AI re-reads rules for gate check → validate → repair loop → repeat

NEW:
  user prompt → wizard (if ambiguity) → AI generates semantic_intent (~30 lines)
              → enrichment_engine.py (deterministic, sub-second)
              → full intent_graph + structured trace log
              → validate_intent.py (mechanical issues should be impossible)
```

`enrichment_rules_T28.md` stays as **AI reference** — still needed for classification guidance, no longer executed mechanically.

## 5. Semantic Intent Format (AI Output Contract)

### Schema

```json
{
  "schema_version": "1.0",
  "tech_node": "T28",
  "ring_config": {
    "width": 4,
    "height": 4,
    "placement_order": "counterclockwise"
  },
  "instances": [
    {
      "name": "VCM",
      "position": "left_0",
      "type": "pad",
      "device": "PDB3AC",
      "domain": "ana_1"
    },
    {
      "name": "RST",
      "position": "left_3",
      "type": "pad",
      "device": "PDDW16SDGZ",
      "domain": "dig_1",
      "direction": "input"
    },
    {
      "name": "D15",
      "position": "top_2_3",
      "type": "inner_pad",
      "device": "PDDW16SDGZ",
      "domain": "dig_1",
      "direction": "output"
    }
  ],
  "domains": {
    "ana_1": {
      "kind": "analog",
      "vdd_provider": "VDDIB",
      "vss_provider": "VSSIB"
    },
    "dig_1": {
      "kind": "digital",
      "low_vdd": "VIOL",
      "low_vss": "GIOL",
      "high_vdd": "VIOH",
      "high_vss": "GIOH"
    }
  },
  "global": {
    "vss_ground": "GIOL",
    "ring_esd": null
  },
  "overrides": {}
}
```

### Field rules (strict)

| Field | Required | Type | Constraint |
|-------|----------|------|------------|
| `schema_version` | Yes | string | Currently `"1.0"` |
| `tech_node` | Yes | string | `"T28"`, `"T180"`, ... |
| `ring_config.width` / `height` | Yes | int | > 0 |
| `ring_config.placement_order` | Yes | string | `"clockwise"` or `"counterclockwise"` |
| `instances[].name` | Yes | string | Signal name as user provided (preserve `<>`) |
| `instances[].position` | Yes | string | `{side}_{idx}` for pads, `{side}_{idx1}_{idx2}` for inner_pads with idx1<idx2 |
| `instances[].type` | Yes | string | `"pad"` or `"inner_pad"` only — engine generates corners |
| `instances[].device` | Yes | string | Base device name; **must NOT end with `_H_G` or `_V_G`** |
| `instances[].domain` | Yes | string | Must exist as key in top-level `domains` |
| `instances[].direction` | Required for digital_io devices | string | `"input"` or `"output"` |
| `domains[].kind` | Yes | string | `"analog"` or `"digital"` |
| `domains[].vdd_provider` / `vss_provider` | Yes (analog) | string | Signal name appearing in instances |
| `domains[].low_vdd` / `low_vss` / `high_vdd` / `high_vss` | Yes (digital) | string | Signal names |
| `global.vss_ground` | Yes | string | Universal VSS label |
| `global.ring_esd` | No | string or null | If set, ring-wide ESD signal name |
| `overrides` | No | object | See §5.2 |

### Removed from v1: `role` field

The device name (PVDD3AC vs PVDD1AC) already encodes provider/consumer. A `role` field is redundant and creates a consistency burden. Removed.

### Pin override semantics

```json
"overrides": {
  "left_3": {
    "pin_overrides": {
      "VSS": "SPECIAL_VSS_BUS"
    }
  },
  "top_5": {
    "pin_overrides": {
      "VDDPST": "label_from:domain.high_vdd"
    }
  }
}
```

| Form | Behavior |
|------|----------|
| Plain string (e.g. `"SPECIAL_VSS_BUS"`) | Used as literal label, no resolution |
| `"label_from:<ref>"` prefix | Resolved through normal `label_from` machinery |

This dual mode keeps simple cases simple (most overrides are one-off literals) while allowing semantic references when needed.

## 6. Device Wiring Table (Corrected)

`assets/device_info/device_wiring_T28.json` — full corrected wiring for all 15 base devices. **Note the corrections to PVSS1AC and PVSS1A from v1.**

```json
{
  "schema_version": "1.0",
  "tech_node": "T28",
  "devices": {
    "PDB3AC": {
      "family": "analog_io",
      "pins": {
        "AIO":    {"label_from": "self"},
        "TACVSS": {"label_from": "domain.vss_provider"},
        "TACVDD": {"label_from": "domain.vdd_provider"},
        "VSS":    {"label_from": "global.vss_ground"}
      }
    },
    "PVDD3AC": {
      "family": "analog_power_provider",
      "pins": {
        "AVDD":   {"label_from": "self_core"},
        "TACVDD": {"label_from": "self"},
        "TACVSS": {"label_from": "domain.vss_provider"},
        "VSS":    {"label_from": "global.vss_ground"}
      }
    },
    "PVSS3AC": {
      "family": "analog_ground_provider",
      "pins": {
        "AVSS":   {"label_from": "self_core"},
        "TACVSS": {"label_from": "self"},
        "TACVDD": {"label_from": "domain.vdd_provider"},
        "VSS":    {"label_from": "global.vss_ground"}
      }
    },
    "PVDD3A": {
      "family": "analog_power_provider",
      "pins": {
        "AVDD":   {"label_from": "self_core"},
        "TAVDD":  {"label_from": "self"},
        "TAVSS":  {"label_from": "domain.vss_provider"},
        "VSS":    {"label_from": "global.vss_ground"}
      }
    },
    "PVSS3A": {
      "family": "analog_ground_provider",
      "pins": {
        "AVSS":   {"label_from": "self_core"},
        "TAVSS":  {"label_from": "self"},
        "TAVDD":  {"label_from": "domain.vdd_provider"},
        "VSS":    {"label_from": "global.vss_ground"}
      }
    },
    "PVDD1AC": {
      "family": "analog_power_consumer",
      "pins": {
        "AVDD":   {"label_from": "self"},
        "TACVDD": {"label_from": "domain.vdd_provider"},
        "TACVSS": {"label_from": "domain.vss_provider"},
        "VSS":    {"label_from": "global.vss_ground"}
      }
    },
    "PVSS1AC": {
      "family": "analog_ground_consumer",
      "pins": {
        "AVSS":   {"label_from": "self"},
        "TACVSS": {"label_from": "domain.vss_provider"},
        "TACVDD": {"label_from": "domain.vdd_provider"},
        "VSS":    {"label_from": "global.vss_ground"}
      },
      "_correction_note": "v2: TACVSS was 'self' in v1 draft; corrected to domain.vss_provider per enrichment_rules_T28.md §3.2"
    },
    "PVDD1A": {
      "family": "analog_power_consumer",
      "pins": {
        "AVDD":   {"label_from": "self"},
        "TAVDD":  {"label_from": "domain.vdd_provider"},
        "TAVSS":  {"label_from": "domain.vss_provider"},
        "VSS":    {"label_from": "global.vss_ground"}
      }
    },
    "PVSS1A": {
      "family": "analog_ground_consumer",
      "pins": {
        "AVSS":   {"label_from": "self"},
        "TAVSS":  {"label_from": "domain.vss_provider"},
        "TAVDD":  {"label_from": "domain.vdd_provider"},
        "VSS":    {"label_from": "global.vss_ground"}
      },
      "_correction_note": "v2: TAVSS was 'self' in v1 draft; corrected to domain.vss_provider"
    },
    "PVSS2A": {
      "family": "analog_esd",
      "pins": {
        "VSS":   {"label_from": "self"},
        "TAVSS": {"label_from": "domain.vss_provider"},
        "TAVDD": {"label_from": "domain.vdd_provider"}
      }
    },
    "PVDD1DGZ": {
      "family": "digital_power_low",
      "pins": {
        "VDD":    {"label_from": "self"},
        "VSS":    {"label_from": "global.vss_ground"},
        "VDDPST": {"label_from": "domain.high_vdd"},
        "VSSPST": {"label_from": "domain.high_vss"},
        "POC":    {"label_from": "const.POC"}
      }
    },
    "PVSS1DGZ": {
      "family": "digital_ground_low",
      "pins": {
        "VSS":    {"label_from": "self"},
        "VDD":    {"label_from": "domain.low_vdd"},
        "VDDPST": {"label_from": "domain.high_vdd"},
        "VSSPST": {"label_from": "domain.high_vss"},
        "POC":    {"label_from": "const.POC"}
      }
    },
    "PVDD2POC": {
      "family": "digital_power_high",
      "pins": {
        "VDDPST": {"label_from": "self"},
        "VDD":    {"label_from": "domain.low_vdd"},
        "VSS":    {"label_from": "global.vss_ground"},
        "VSSPST": {"label_from": "domain.high_vss"},
        "POC":    {"label_from": "const.POC"}
      }
    },
    "PVSS2DGZ": {
      "family": "digital_ground_high",
      "pins": {
        "VSSPST": {"label_from": "self"},
        "VDD":    {"label_from": "domain.low_vdd"},
        "VSS":    {"label_from": "global.vss_ground"},
        "VDDPST": {"label_from": "domain.high_vdd"},
        "POC":    {"label_from": "const.POC"}
      }
    },
    "PDDW16SDGZ": {
      "family": "digital_io",
      "pins": {
        "PAD":    {"label_from": "self"},
        "VDD":    {"label_from": "domain.low_vdd"},
        "VSS":    {"label_from": "global.vss_ground"},
        "VDDPST": {"label_from": "domain.high_vdd"},
        "VSSPST": {"label_from": "domain.high_vss"},
        "POC":    {"label_from": "const.POC"},
        "REN":    {"label_from": "io.ren"},
        "OEN":    {"label_from": "io.oen"},
        "C":      {"label_from": "io.c"},
        "I":      {"label_from": "io.i"}
      },
      "io_direction_rules": {
        "input": {
          "REN": {"label_from": "global.vss_ground"},
          "OEN": {"label_from": "domain.low_vdd"},
          "C":   {"label_from": "self_core"},
          "I":   {"label_from": "global.vss_ground"}
        },
        "output": {
          "REN": {"label_from": "domain.low_vdd"},
          "OEN": {"label_from": "global.vss_ground"},
          "C":   {"label_from": "const.noConn"},
          "I":   {"label_from": "self_core"}
        }
      }
    },
    "PRUW08SDGZ": {
      "family": "digital_io",
      "pins": {
        "PAD":    {"label_from": "self"},
        "VDD":    {"label_from": "domain.low_vdd"},
        "VSS":    {"label_from": "global.vss_ground"},
        "VDDPST": {"label_from": "domain.high_vdd"},
        "VSSPST": {"label_from": "domain.high_vss"},
        "POC":    {"label_from": "const.POC"},
        "REN":    {"label_from": "io.ren"},
        "OEN":    {"label_from": "io.oen"},
        "C":      {"label_from": "io.c"},
        "I":      {"label_from": "io.i"}
      },
      "io_direction_rules": {
        "input": {
          "REN": {"label_from": "domain.low_vdd"},
          "OEN": {"label_from": "domain.low_vdd"},
          "C":   {"label_from": "self_core"},
          "I":   {"label_from": "global.vss_ground"}
        },
        "output": {
          "REN": {"label_from": "domain.low_vdd"},
          "OEN": {"label_from": "global.vss_ground"},
          "C":   {"label_from": "const.noConn"},
          "I":   {"label_from": "self_core"}
        }
      }
    }
  }
}
```

### `label_from` reference taxonomy

| Reference | Resolves to | Resolution context |
|-----------|-------------|---------------------|
| `self` | Instance's own `name` | Per-instance |
| `self_core` | Instance `name` + `_CORE` | Per-instance |
| `domain.vdd_provider` / `vss_provider` | From analog domain definition | Per-instance via `instance.domain` |
| `domain.low_vdd` / `low_vss` / `high_vdd` / `high_vss` | From digital domain definition | Per-instance via `instance.domain` |
| `global.vss_ground` | From `semantic_intent.global.vss_ground` (or `ring_esd` if active) | Whole-ring |
| `const.POC` / `const.noConn` | Literal strings | Static |
| `io.ren` / `io.oen` / `io.c` / `io.i` | Recurses through `io_direction_rules[direction]` | Per-instance, requires `direction` |

Resolution is single-pass with cycle detection.

## 7. Wiring Table Validation (Load-Time)

The engine validates the wiring table at load time before processing any input. This catches authoring errors (like the v1 bugs I missed) immediately.

| Check | Failure mode |
|-------|--------------|
| Every device has a `family` | Hard error |
| Every device has at least one pin | Hard error |
| Every `label_from` reference is in the taxonomy | Hard error with valid list |
| `digital_io` devices have `io_direction_rules` | Hard error |
| `io_direction_rules` covers both `input` and `output` | Hard error |
| Pin names match those in `IO_device_info_T28.json` for the same device | Hard error (cross-check) |
| Provider devices use `self_core` for AVDD/AVSS | Warning (suspicious if not) |
| Consumer devices do NOT use `self_core` | Warning |
| `analog_*_consumer` device's TACVSS/TAVSS uses `domain.vss_provider` | Warning (catches v1's bug class) |

The cross-check against `IO_device_info_T28.json` is critical: ensures that every pin we're wiring actually exists in the PDK template.

## 8. Engine Logic (Updated)

```
enrich(semantic_intent) → full_intent_graph + trace_log:

  # Phase 0: Load + validate wiring table (cached)
  Load device_wiring_T28.json
  Validate per §7
  Cross-check with IO_device_info_T28.json

  # Phase 1: Validate semantic intent input
  - schema_version matches engine version
  - All instances reference valid domains
  - All device names exist in wiring table
  - No suffixes on device names
  - Inner pad positions: idx1 < idx2, both in range
  - Digital IO instances have direction
  - Domain provider names appear in instances list (sanity check)

  # Phase 2: Expand instances
  for each instance in semantic_intent.instances:
    1. Extract side from position
    2. Compute suffix: left/right → _H_G, top/bottom → _V_G
    3. Full device name = device + suffix
    4. Look up wiring table entry → pin definitions
    5. For each pin:
       a. If overrides[position].pin_overrides[pin_name] exists:
          - Plain string → use as literal label
          - "label_from:<ref>" → resolve via normal machinery
       b. Else: resolve label_from per §6 taxonomy
    6. Build pin_connection dict
    7. Build output instance: name, device (full), position, type, direction, pin_connection

  # Phase 3: Generate corners
  for each corner_position in [top_left, top_right, bottom_left, bottom_right]:
    1. Find adjacent pads per placement_order
    2. Look up family of both adjacent pad devices
    3. Both digital → PCORNER_G, otherwise → PCORNERA_G
    4. Insert corner at correct list position per placement_order

  # Phase 4: Ring ESD override (if active)
  if global.ring_esd is set:
    For every pad in ring (analog AND digital, including providers):
      Override VSS pin_connection.label = global.ring_esd

  # Phase 5: Gate checks (all must pass)
  G1. Side counts: top/bottom = width, left/right = height (outer pads only)
  G2. All 4 corners present, types match adjacent devices
  G3. Digital provider count = exactly 4 unique names IF design has digital domain
      (skip if pure analog)
  G4. VSS consistency: all pads' VSS pin_connection.label identical
      (or all = ring_esd if active)
  G5. Required pins present per device (digital: VDD/VSS/VDDPST/VSSPST; analog: VSS)
  G6. Digital IO has direction field; non-digital-IO does NOT
  G7. Ring ESD: PVSS2A only in analog domains, PVSS1DGZ only in digital
  G8. Domain continuity (NEW in v2):
      For each analog domain, signals form contiguous block(s) (with ring wrap).
      If multiple blocks per domain, each block must have its own provider pair.
      Digital signals form single contiguous block (with ring wrap).
      Failures are warnings, not errors — AI may have intentional discontinuity.

  # Phase 6: Output
  Write intent_graph.json (deterministic field order)
  Write trace_log.json alongside (per-instance resolution log + gate results)
```

## 9. Engine Output Schema (Field-by-Field)

The engine produces `io_ring_intent_graph.json` matching today's format exactly:

```json
{
  "ring_config": {
    "width": <int>,
    "height": <int>,
    "placement_order": "<clockwise|counterclockwise>"
  },
  "instances": [
    {
      "name": "<string>",
      "device": "<base_device>_<suffix>",
      "position": "<position_string>",
      "type": "<pad|inner_pad|corner>",
      "direction": "<input|output>",
      "pin_connection": {
        "<pin_name>": {"label": "<resolved_label>"}
      }
    }
  ]
}
```

Field ordering within each instance object: `name, device, position, type, direction, pin_connection` (in that order). Pin order within `pin_connection`: as defined in the wiring table for that device. This determinism makes diffs against goldens meaningful.

## 10. Trace Log Format

Alongside the intent graph, the engine writes `enrichment_trace.json`:

```json
{
  "engine_version": "1.0",
  "wiring_table_version": "1.0",
  "input_path": "...",
  "output_path": "...",
  "duration_ms": 47,
  "instances": [
    {
      "position": "left_0",
      "name": "VCM",
      "input_device": "PDB3AC",
      "computed_suffix": "_H_G",
      "full_device": "PDB3AC_H_G",
      "pins": [
        {"name": "AIO", "label_from": "self", "resolved": "VCM"},
        {"name": "TACVSS", "label_from": "domain.vss_provider", "resolved": "VSSIB", "domain": "ana_1"},
        ...
      ],
      "overrides_applied": []
    }
  ],
  "corners": [
    {"position": "top_left", "adjacent": ["top_3", "left_0"], "family_pair": ["analog_io", "analog_io"], "type": "PCORNERA_G"}
  ],
  "esd_override_applied": false,
  "gates": {
    "G1_side_counts": {"pass": true},
    "G3_digital_provider_count": {"pass": true, "providers": {"low_vdd": "VIOL", "low_vss": "GIOL", "high_vdd": "VIOH", "high_vss": "GIOH"}},
    "G8_domain_continuity": {"pass": true, "warnings": []}
  }
}
```

Used for: debugging AI mistakes, regression diffing, support tickets, future analytics on AI classification accuracy.

## 11. Wizard Integration

The wizard (defined in `wizard_T28.md`) handles ambiguity. In v2, wizard runs **before** the AI generates semantic intent:

```
user prompt
  → Step 0: directory setup
  → Step 1: image processing (if applicable)
  → Step 2: AI builds draft JSON (structural only, unchanged)
  → Step 2b: draft editor (if enabled)
  → Step 2.5 (NEW): AI checks for ambiguity per wizard_T28.md
       - If ambiguous (signal type, voltage domain boundary, direction)
         → invoke wizard, collect wizard_constraints
       - Else: skip
  → Step 3a (NEW): AI generates semantic_intent.json
       - Inputs: draft JSON, user prompt, wizard_constraints (if any), draft editor hints
       - Constraint precedence: user prompt > draft editor > wizard_constraints > AI inference
  → Step 3b (NEW): Run enrichment_engine.py
       - Outputs: io_ring_intent_graph.json + enrichment_trace.json
  → Step 4: Reference-guided gate check (mostly redundant now, kept as safety net)
  → Step 5: validate_intent.py
  ... (rest unchanged)
```

The wizard's output schema (in `wizard_T28.md`) doesn't change. The AI consumes wizard_constraints when generating semantic_intent — same constraints, smaller output format.

## 12. Rollback Strategy

### Phase A: Side-by-side mode (first 2 weeks)

Both old and new flows run; outputs are diffed. Discrepancies logged but old flow's output is used downstream.

```bash
export AMS_ENGINE_MODE=compare   # default during rollout
```

The compare mode:
1. Run AI's old direct-generation flow → `intent_graph_legacy.json`
2. Run new flow (semantic intent + engine) → `intent_graph_engine.json`
3. Diff the two; log to `engine_compare_<timestamp>.json`
4. Use legacy output for Steps 6-12

After 2 weeks of clean diffs, switch to:

### Phase B: Engine-primary mode (production)

```bash
export AMS_ENGINE_MODE=engine    # production
```

Engine output is used. Legacy flow is not invoked. `AMS_ENGINE_MODE=legacy` remains available as escape hatch for emergencies.

### Phase C: Legacy retired (after 1 month clean)

Legacy flow code path remains in repo but is gated behind a deprecation warning. Removal happens in a separate PR after another month.

## 13. Test Plan

### Unit tests (new: `tests/unit/test_enrichment_engine.py`)

- `test_suffix_left_right_returns_H_G`
- `test_suffix_top_bottom_returns_V_G`
- `test_inner_pad_position_extracts_side`
- `test_label_from_self_returns_instance_name`
- `test_label_from_self_core_appends_CORE`
- `test_label_from_domain_vdd_provider_resolves`
- `test_label_from_global_vss_ground_resolves`
- `test_label_from_io_ren_input_pddw16_returns_global_vss`
- `test_label_from_io_ren_input_pruw08_returns_domain_low_vdd`
- `test_pin_override_literal_used_as_is`
- `test_pin_override_label_from_prefix_resolved`
- `test_corner_both_digital_neighbors_returns_PCORNER_G`
- `test_corner_mixed_neighbors_returns_PCORNERA_G`
- `test_ring_esd_active_overrides_all_VSS`
- `test_gate_G1_side_count_mismatch_fails`
- `test_gate_G3_digital_provider_count_5_fails`
- `test_gate_G3_pure_analog_design_skipped`
- `test_gate_G4_VSS_inconsistency_fails`
- `test_gate_G8_domain_continuity_warns_on_split`

### Wiring table validation tests

- `test_load_validates_label_from_taxonomy`
- `test_load_cross_checks_pins_against_pdk_json`
- `test_load_warns_on_consumer_with_self_core`
- `test_load_warns_on_consumer_TACVSS_self` (would have caught v1 bug)

### Integration tests (30 goldens)

- `test_golden_<case_name>` for each of the 30 testbench cases
- Each loads `semantic_intent_<case>.json` (generated in Phase 0)
- Runs engine, diffs against `golden_output/<case>/io_ring_intent_graph.json`

### Smoke test on rollback

- `test_compare_mode_legacy_and_engine_diff_logged`
- `test_engine_failure_falls_back_to_legacy_in_compare_mode`

## 14. Implementation Order (Realistic)

| Phase | What | Effort | Dependencies |
|-------|------|--------|--------------|
| **0a** | Domain expert review of wiring table | 0.5 day | — |
| **0b** | Generate `semantic_intent_<case>.json` for all 30 goldens (manual reverse-engineering from golden intent_graphs) | 2 days | 0a |
| **1** | Create `device_wiring_T28.json` (with corrections, after expert review) | 0.5 day | 0a |
| **2** | Implement engine: load + validate wiring, suffix logic, label resolution | 1.5 days | 1 |
| **3** | Implement corner generation | 0.5 day | 2 |
| **4** | Implement gate checks (G1-G8) | 1 day | 2 |
| **5** | Implement Ring ESD override | 0.5 day | 2 |
| **6** | CLI wrapper `scripts/enrich_intent.py` + structured trace logging | 0.5 day | 2-5 |
| **7** | Unit tests (parallelizable with 2-6) | 1 day | 2 |
| **8** | Run engine against 30 goldens, fix discrepancies | 1-2 days | 0b, 2-6 |
| **9** | Implement compare mode + AMS_ENGINE_MODE flag | 0.5 day | 6 |
| **10** | Rewrite SKILL.md Steps 2-5 (prompt engineering) | 0.5 day | 6 |
| **11** | Add banner to enrichment_rules_T28.md | 15 min | 10 |
| **12** | Internal smoke test on 5 fresh designs | 0.5 day | All |
| **Total** | | **~9 days** | |

Phases 7 and 8 can run in parallel with later phases. Critical path is 0a → 0b → 1 → 2 → 8.

## 15. Rollout Checklist

Before flipping to `AMS_ENGINE_MODE=engine`:

- [ ] All 30 golden test cases pass (integration tests)
- [ ] All unit tests pass
- [ ] Wiring table validated by domain expert (signed off)
- [ ] Compare mode run on ≥ 50 fresh designs over 2 weeks
- [ ] Discrepancy rate from compare mode < 1% over last 7 days
- [ ] DRC pass rate equal-or-better than legacy in compare period
- [ ] LVS pass rate equal-or-better than legacy in compare period
- [ ] Trace log format reviewed and approved
- [ ] Rollback procedure documented and tested

## 16. What This Plan Does NOT Cover

Explicitly out of scope, to be handled separately:

- **Voltage/current-driven device selection** — future AI feature; engine is ready when AI is
- **Chip-image-driven device selection** — future AI feature; engine is ready when AI is
- **Multi-tech-node engine** (T180, T22) — engine logic is tech-agnostic but per-node wiring tables and goldens needed
- **Filler insertion optimizations** — Step 6's `auto_filler.py` unchanged
- **DRC/LVS repair loop logic** — Steps 10-11 unchanged
- **Wizard rule changes** — `wizard_T28.md` unchanged

## 17. Files Modified vs Untouched

### New
- `assets/core/layout/enrichment_engine.py` (~350 lines)
- `assets/device_info/device_wiring_T28.json` (~250 lines)
- `scripts/enrich_intent.py` (~80 lines)
- `tests/unit/test_enrichment_engine.py` (~600 lines)
- `tests/integration/test_goldens.py` (~100 lines)
- `T28_Testbench/semantic_intents/IO_28nm_*.json` × 30 (Phase 0b output)

### Modified
- `SKILL.md` — Steps 2-5 rewritten (prompt engineering, ~2 hours)
- `references/enrichment_rules_T28.md` — banner added
- Optional: `scripts/build_confirmed_config.py` — accept either legacy or engine output (compare mode plumbing)

### Untouched
- `IO_device_info_T28.json` and parser
- `validate_intent.py`
- `generate_schematic.py`, `generate_layout.py`
- `run_drc.py`, `run_lvs.py`, `run_il_with_screenshot.py`
- `auto_filler.py`, `confirmed_config_builder.py`
- `draft_builder_T28.md`, `wizard_T28.md`
- All Step 7-12 infrastructure

## 18. Open Questions for User

1. **Domain expert availability**: Phase 0a needs an experienced T28 designer to review the wiring table line-by-line. Who?
2. **Compare mode period**: Plan suggests 2 weeks. Acceptable, or longer/shorter?
3. **Failure-mode policy**: When engine and legacy disagree in compare mode, which output is canonical for that run? Plan says legacy by default for safety; alternative is engine.
4. **Pin override scope**: Should pin overrides be allowed in production semantic intents, or restricted to debug/development only? Plan currently allows in production; restricting would prevent escape-hatch abuse.
5. **Trace log retention**: How long do we keep `enrichment_trace.json` files? Plan doesn't specify cleanup.

---

## Summary of v2 Changes

v2 turns the v1 sketch into an implementable plan by:

1. **Fixing wiring table bugs** — PVSS1AC and PVSS1A consumers had `TACVSS/TAVSS → self`, now correctly `domain.vss_provider`.
2. **Adding load-time wiring validation** — catches the bug class that produced v1's errors.
3. **Adding gate G8** — domain continuity check, the most common AI semantic error.
4. **Specifying override syntax** — literal vs `label_from:` prefix.
5. **Removing redundant `role` field** — device name is single source of truth.
6. **Adding rollback strategy** — compare mode, then engine-primary, then legacy retirement.
7. **Adding structured trace logging** — debuggability and analytics.
8. **Generating golden semantic intents in Phase 0b** — concrete input contract before engine work.
9. **Honest 9-day timeline** with parallelizable phases.
10. **Test plan** — unit, wiring-validation, integration, rollback smoke tests.
11. **Open questions** — flagging decisions that need user input before starting.

The architectural direction is unchanged from v1. v2 is the engineering plan that makes v1's idea robust enough to ship.
