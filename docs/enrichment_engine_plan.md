# Enrichment Engine Plan

> Hybrid AI+code architecture for T28 IO Ring enrichment (Steps 2-5).
> AI owns semantic decisions. Code owns mechanical execution.

---

## 1. Problem Statement

Today, Steps 2-5 of the T28 pipeline are entirely AI-driven: Claude reads ~700 lines of enrichment rules (`enrichment_rules_T28.md`), reasons about every signal's device, pins, and corners in natural language, then generates JSON. This has three failure modes:

| Problem | Root cause |
|---------|-----------|
| **Hallucinated pin labels** | AI must remember suffix rules, `_CORE` rules, domain provider names for every pin |
| **Repair loops** | Steps 4-5 exist solely to catch AI mistakes → re-read rules → fix → re-validate |
| **Token burn** | ~17K tokens of enrichment rules consumed every run |

However, some decisions genuinely require AI judgment — which device to choose (PVDD3AC vs PVDD3A), how to group voltage domains, what direction a signal is. Codifying these would create rigidity.

## 2. The Split

```
AI OWNS (semantic — needs design judgment, changes per project)
══════════════════════════════════════════════════════════════
  signal class      analog_io / digital_io / analog_power_provider / ...
  device choice     PDB3AC vs PDB4BC, PVDD3AC vs PVDD3A
  domain grouping   which signals share a voltage domain
  provider names    which signals are VDD/VSS providers per domain
  direction         input vs output (digital IO)
  ring ESD          whether ring-wide ESD is active, signal name

CODE OWNS (mechanical — fixed by PDK, zero judgment, zero errors)
══════════════════════════════════════════════════════════════
  suffix            left/right → _H_G, top/bottom → _V_G
  pin wiring        every pin on every device, wired to correct domain signal
  _CORE suffix      AVDD/AVSS on provider devices → {name}_CORE
  IO direction pins REN/OEN/C/I behavior (input vs output)
  corners           check 2 adjacent pad devices → PCORNER_G or PCORNERA_G
  gate checks       continuity, provider count=4, VSS consistency
```

**The device name is the handoff point.** AI says *which* device. Code says *how* it's wired.

## 3. Data Flow

```
OLD (AI does everything):
  user prompt
    → AI reads 700 lines enrichment_rules_T28.md
    → AI generates full intent_graph.json (200+ lines, all pins wired)
    → AI reads rules again for gate check (Step 4)
    → validate_intent.py (Step 5)
    → repair loop (AI fixes mistakes, re-validates)
    → repeat until clean

NEW (engine does mechanical):
  user prompt
    → AI reads enrichment_rules_T28.md (still needed for classification guidance)
    → AI generates semantic_intent.json (~30 lines, device names only, no pins)
    → enrichment_engine.py (sub-second, deterministic)
    → full intent_graph.json
    → validate_intent.py (Step 5, first-pass pass rate near 100%)
```

The `enrichment_rules_T28.md` stays as **reference documentation** for the AI — it still needs to know the classification rules to make semantic decisions. But the AI no longer executes the mechanical rules.

## 4. Semantic Intent Format (AI Output)

The AI produces a lightweight file containing only semantic decisions:

```json
{
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
      "domain": "ana_1",
      "direction": null,
      "role": "consumer"
    },
    {
      "name": "VDDIB",
      "position": "left_1",
      "type": "pad",
      "device": "PVDD3AC",
      "domain": "ana_1",
      "direction": null,
      "role": "vdd_provider"
    },
    {
      "name": "VSSIB",
      "position": "left_2",
      "type": "pad",
      "device": "PVSS3AC",
      "domain": "ana_1",
      "direction": null,
      "role": "vss_provider"
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
      "vdd_provider": "VDDIB",
      "vss_provider": "VSSIB"
    },
    "dig_1": {
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

### Field rules

| Field | Required | Values |
|-------|----------|--------|
| `name` | Yes | Signal name as provided by user |
| `position` | Yes | `{side}_{idx}` for pads, `{side}_{idx1}_{idx2}` for inner_pads |
| `type` | Yes | `pad`, `inner_pad`, or `corner` |
| `device` | Yes | **Base device name without suffix** (e.g. `PDB3AC`, not `PDB3AC_H_G`) |
| `domain` | Yes | Domain ID (must exist in `domains` map) |
| `direction` | Digital IO only | `input` or `output` |
| `role` | Analog power only | `vdd_provider`, `vss_provider`, or `consumer` |

**The AI must NOT include corners in `instances`.** The engine generates corners automatically.

**The AI must NOT include suffixes on device names.** The engine adds `_H_G`/`_V_G` based on position. If a device name ends with `_H_G` or `_V_G`, the engine errors.

**The AI must use position-indexed identity.** Same signal name at different positions is normal (e.g. VSSIB as provider at left_1, VSSIB as consumer at left_5). Each position is processed independently.

### Override system (escape hatches)

The `overrides` field allows the AI to bypass any engine decision:

```json
"overrides": {
  "left_3": {
    "pin_overrides": {
      "VSS": "SPECIAL_VSS"
    }
  },
  "top_0": {
    "device_suffix_override": "PDB3AC_X_G"
  }
}
```

| Override | Scope | Use case |
|----------|-------|----------|
| `pin_overrides` | Per-position, per-pin | New device with non-standard pin wiring |
| `device_suffix_override` | Per-position | Custom suffix for experimental device variant |

The engine applies overrides after resolving all rules, so they always win.

## 5. Device Wiring Table (New Data File)

`assets/device_info/device_wiring_T28.json` — maps each base device name to its pin semantic sources:

```json
{
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
      "TACVSS": {"label_from": "self"},
      "TACVDD": {"label_from": "domain.vdd_provider"},
      "VSS":    {"label_from": "global.vss_ground"}
    }
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
      "TAVSS":  {"label_from": "self"},
      "TAVDD":  {"label_from": "domain.vdd_provider"},
      "VSS":    {"label_from": "global.vss_ground"}
    }
  },
  "PVSS2A": {
    "family": "analog_esd",
    "pins": {
      "VSS":    {"label_from": "self"},
      "TAVSS":  {"label_from": "domain.vss_provider"},
      "TAVDD":  {"label_from": "domain.vdd_provider"}
    }
  },
  "PVDD1DGZ": {
    "family": "digital_power_low",
    "pins": {
      "VDD":    {"label_from": "self"},
      "VSS":    {"label_from": "domain.low_vss"},
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
      "VSS":    {"label_from": "domain.low_vss"},
      "VSSPST": {"label_from": "domain.high_vss"},
      "POC":    {"label_from": "const.POC"}
    }
  },
  "PVSS2DGZ": {
    "family": "digital_ground_high",
    "pins": {
      "VSSPST": {"label_from": "self"},
      "VDD":    {"label_from": "domain.low_vdd"},
      "VSS":    {"label_from": "domain.low_vss"},
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
```

### `label_from` reference types

| Reference | Resolves to | Example |
|-----------|-------------|---------|
| `self` | Instance's own `name` | `VCM` → `VCM` |
| `self_core` | Instance `name` + `_CORE` | `VDDIB` → `VDDIB_CORE` |
| `domain.vdd_provider` | VDD provider name for this instance's domain | `VDDIB` |
| `domain.vss_provider` | VSS provider name for this instance's domain | `VSSIB` |
| `domain.low_vdd` | Digital domain low-voltage VDD | `VIOL` |
| `domain.low_vss` | Digital domain low-voltage VSS | `GIOL` |
| `domain.high_vdd` | Digital domain high-voltage VDD | `VIOH` |
| `domain.high_vss` | Digital domain high-voltage VSS | `GIOH` |
| `global.vss_ground` | Universal VSS ground (or ESD signal if active) | `GIOL` |
| `const.POC` | Literal `"POC"` | `POC` |
| `const.noConn` | Literal `"noConn"` | `noConn` |
| `io.ren` | Resolved by `io_direction_rules` based on `direction` | `GIOL` or `VIOL` |
| `io.oen` | Resolved by `io_direction_rules` based on `direction` | `VIOL` or `GIOL` |
| `io.c` | Resolved by `io_direction_rules` based on `direction` | `VCM_CORE` or `noConn` |
| `io.i` | Resolved by `io_direction_rules` based on `direction` | `GIOL` or `VCM_CORE` |

### Adding a new device (no Python changes)

To add a new PDK device, add one entry to the wiring JSON:

```json
"PDB4BC": {
  "family": "analog_io",
  "pins": {
    "AIO":    {"label_from": "self"},
    "TACVSS": {"label_from": "domain.vss_provider"},
    "TACVDD": {"label_from": "domain.vdd_provider"},
    "VSS":    {"label_from": "global.vss_ground"},
    "VDDCORE": {"label_from": "domain.vdd_provider"}
  }
}
```

The AI can immediately select `"device": "PDB4BC"` in the semantic intent and the engine wires it correctly. No Python changes. If the device has pins not covered by existing `label_from` types, the AI uses `pin_overrides` for those specific pins until the wiring JSON is updated.

## 6. Engine Logic (Pseudocode)

```
enrich(semantic_intent) → full_intent_graph:

  # Phase 1: Expand instances
  for each instance in semantic_intent.instances:
    1. Validate device name has no suffix (_H_G or _V_G)
    2. Extract side from position (left/right/top/bottom)
    3. Compute suffix: left/right → _H_G, top/bottom → _V_G
    4. Full device name = device + suffix
    5. Look up device in wiring table → get pin definitions
    6. For each pin:
       a. Resolve label_from → concrete label name
          - Resolve domain.* references against instance.domain in semantic_intent.domains
          - Resolve global.* references against semantic_intent.global
          - Resolve io.* references through io_direction_rules if instance has direction
       b. If pin_overrides exist for this position+pin, use override label
    7. Build pin_connection dict: {pin_name: {"label": resolved_label}}
    8. Build output instance with: name, device (full), position, type, direction (if set), pin_connection

  # Phase 2: Generate corners
  for each corner_position in [top_left, top_right, bottom_left, bottom_right]:
    1. Find two adjacent pads based on placement_order
       - Counterclockwise: top_left→(top_{w-1}, left_0), top_right→(top_0, right_{h-1}),
         bottom_left→(left_{h-1}, bottom_0), bottom_right→(bottom_{w-1}, right_0)
       - Clockwise: top_left→(left_{h-1}, top_0), top_right→(top_{w-1}, right_0),
         bottom_left→(bottom_{w-1}, left_0), bottom_right→(right_{h-1}, bottom_0)
    2. Check device family of both adjacent pads (from wiring table)
       - digital devices: PDDW16SDGZ, PRUW08SDGZ, PVDD1DGZ, PVSS1DGZ, PVDD2POC, PVSS2DGZ
       - analog devices: everything else
    3. Both digital → PCORNER_G, otherwise → PCORNERA_G
    4. Insert corner at correct position in traversal order:
       - Clockwise: top_right → bottom_right → bottom_left → top_left
       - Counterclockwise: bottom_left → bottom_right → top_right → top_left

  # Phase 3: Gate checks
  G1. Digital provider count = exactly 4 unique signal names
      (1 low_vdd, 1 low_vss, 1 high_vdd, 1 high_vss)
  G2. VSS consistency: all pads' VSS pin_connection → same label
      (unless Ring ESD is active → all point to ESD signal name)
  G3. Corner count = 4
  G4. All 4 required pins present on digital pads (VDD, VSS, VDDPST, VSSPST)
  G5. All analog pads have VSS pin
  G6. Digital IO pads have direction field
  G7. Ring ESD active → PVSS2A in analog domain, PVSS1DGZ in digital domain;
      every pad's VSS → ESD signal name

  # Phase 4: Ring ESD override
  If global.ring_esd is set:
    For every pad in the ring:
      VSS pin_connection label → ring_esd signal name

  # Phase 5: Output
  Write full intent_graph.json in standard format
```

## 7. Engine Integration

### New files

| File | Description | Lines (est.) |
|------|-------------|--------------|
| `assets/core/layout/enrichment_engine.py` | Core engine: expand instances, resolve pins, generate corners, run gates | ~300 |
| `assets/device_info/device_wiring_T28.json` | Device → pin semantic wiring table | ~200 |
| `scripts/enrich_intent.py` | CLI entry point: `python enrich_intent.py semantic.json intent_graph.json T28` | ~60 |

### Modified files

| File | Change |
|------|--------|
| `SKILL.md` | Steps 2-5: replace "AI reads enrichment_rules, generates full JSON" with "AI generates semantic_intent → run enrich_intent.py → run validate_intent.py" |
| `references/enrichment_rules_T28.md` | Keep as AI reference. Add banner: "This document guides the AI in making semantic decisions. Pin wiring, suffix rules, and corner generation are handled automatically by the enrichment engine." |

### Unchanged files

| File | Why untouched |
|------|--------------|
| `IO_device_info_T28.json` | Still used by layout/schematic generators for physical pin data |
| `IO_device_info_T28_parser.py` | Still used by SKILL generators; engine calls `get_pin_config()` for IO direction logic |
| `validate_intent.py` | Still validates final output (same format) |
| `build_confirmed_config.py` | Still adds fillers, opens editor — consumes same format |
| `generate_schematic.py`, `generate_layout.py` | Consume confirmed.json in same format |
| `run_drc.py`, `run_lvs.py`, `run_il_with_screenshot.py` | Unchanged |
| `draft_builder_T28.md` | Step 2 still builds draft JSON (structural only) same as today |
| `wizard_T28.md` | Wizard resolves ambiguity before semantic intent generation, same as today |

## 8. Verge Conditions (Addressed)

### Duplicate signal names, different roles

Engine processes by **position index**, never by name. Two instances with `name: "VSSIB"` at `left_1` (provider) and `left_5` (consumer) are processed independently. Each resolves `domain.*` references against its own domain. No cross-contamination.

### New PDK device added

Add one entry to `device_wiring_T28.json`. AI can immediately select it. Zero Python changes. If the device uses pins not covered by existing `label_from` types, the AI uses `pin_overrides` as a temporary escape hatch.

### Device-specific pin exceptions

Three-tier override:
1. **Wiring table** — standard behavior for the device family
2. **`io_direction_rules`** — per-direction pin overrides within the wiring table (handles PDDW16 vs PRUW08 input differences)
3. **AI `pin_overrides`** — per-instance, per-pin override for one-off cases

Example: a hypothetical device `PDB3BC` has the same pins as `PDB3AC` but its VSS pin must connect to a special net. The AI sets:

```json
"left_4": {
  "device": "PDB3BC",
  "pin_overrides": {"VSS": "SPECIAL_VSS_BUS"}
}
```

### Ring ESD

When `global.ring_esd` is set to a signal name, the engine overrides every pad's VSS pin to point to that name. PVSS2A in analog domains uses `label_from: self` for its VSS pin (correct — it IS the ESD pad). PVSS1DGZ in digital domains uses standard digital VSS wiring. The override is applied in Phase 4 after all normal resolution.

### Context troubleshooting

Every engine decision produces a trace line. On gate failure, the error message includes:

```
[GATE-ERR] G1: Digital provider count is 5, expected exactly 4 unique names.
  Extra provider: "EXTRA_VDD" at position top_3 (device=PVDD1DGZ)
  Hint: "EXTRA_VDD" may belong to an analog voltage domain. Check domain assignment.
  Current digital providers:
    low_vdd=VIOL (top_2), low_vss=GIOL (top_5),
    high_vdd=VIOH (top_7), high_vss=GIOH (top_8),
    EXTRA=EXTRA_VDD (top_3) ← UNEXPECTED
```

## 9. Regression Safety

The 30 golden test cases in `T28_Testbench/golden_output/` serve as acceptance tests:

1. For each test case, run the AI to produce `semantic_intent.json`
2. Run `enrich_intent.py` to produce `io_ring_intent_graph.json`
3. Diff against `golden_output/<case>/io_ring_intent_graph.json`
4. Any difference is either:
   - **Engine bug** — fix the engine
   - **AI was wrong, engine is right** — update the golden (the whole point)
   - **Engine is wrong** — fix the wiring table or engine logic

## 10. Future-Proofing

### When the AI starts using chip pictures for device selection

The enrichment engine doesn't care *how* the AI chose `PDB3AC` — only that it did. Whether the AI inferred the device from signal names, a chip floorplan image, or voltage/current specs, the engine wires it the same way. The device name is a stable contract.

### When device classification rules are unified/improved

The `enrichment_rules_T28.md` can be rewritten, simplified, or replaced without touching the engine. The engine only needs: device name + position + domain + direction → correct pin_connection.

### When a new technology node is added (e.g. T22)

Create `device_wiring_T22.json` with that node's devices. The engine reads the wiring table path from the tech_node parameter. The engine logic (suffix rules, pin resolution, corner generation, gates) is technology-agnostic — only the wiring table changes.

## 11. Implementation Order

| Phase | What | Risk |
|-------|------|------|
| **1** | Create `device_wiring_T28.json` with all 15 current device types | Low — data-only, testable in isolation |
| **2** | Implement `enrichment_engine.py` core: suffix + pin resolution | Medium — must match existing behavior |
| **3** | Implement corner generation in engine | Low — pure rule application |
| **4** | Implement gate checks | Low — validates engine output |
| **5** | Create `scripts/enrich_intent.py` CLI | Low — thin wrapper |
| **6** | Run all 30 golden cases through engine, fix discrepancies | Medium — iterative |
| **7** | Update `SKILL.md` Steps 2-5 to use new flow | Low — documentation change |
| **8** | Add `enrichment_rules_T28.md` banner | Low — documentation |

Phases 1-5 can be done without changing any existing code — the engine is additive. Phase 6 validates correctness. Phases 7-8 switch the pipeline over.

## 12. What Does NOT Change

- **Step 0** (directory setup, Python resolution) — unchanged
- **Step 1** (image input processing) — unchanged
- **Step 2** (draft JSON builder) — unchanged, still AI-driven structural only
- **Step 2b** (draft editor) — unchanged, edits flow into AI's semantic intent
- **Wizard** — unchanged, resolves ambiguity before semantic intent
- **Step 6** (confirmed config, filler insertion, layout editor) — unchanged
- **Steps 7-12** (SKILL generation, Virtuoso execution, DRC/LVS) — unchanged
- **`validate_intent.py`** — unchanged, same output format
- **`IO_device_info_T28.json` and parser** — unchanged, still used by generators
