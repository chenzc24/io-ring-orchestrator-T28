# Enrichment Engine — Testing Guide

> Handoff doc for the next agent / human tester. Covers: what's been built, what's been verified, what to test next, how to file bugs, and what's explicitly NOT yet covered.

---

## 1. What Exists Now

### New artifacts

| Path | Status |
|------|--------|
| `assets/device_info/device_wiring_T28.json` | Written, validated by load-time checks |
| `assets/core/layout/enrichment_engine.py` | Written, smoke-tested, one bug fixed during testing (domain-not-defined error message) |
| `scripts/enrich_intent.py` | Written, exit codes 0/1/2/3 verified |
| `T28_Testbench/semantic_intents/IO_28nm_3x3_single_ring_analog.json` | Hand-crafted golden semantic intent |
| `T28_Testbench/semantic_intents/IO_28nm_3x3_single_ring_mixed.json` | Hand-crafted golden semantic intent |
| `references/enrichment_rules_T28.md` | Restructured: 706 → 432 lines, classification preserved, mechanical sections moved out, new §4 Output Format and §6 Engine Interaction |
| `SKILL.md` | Steps 3-4 rewritten, Steps 5-11 renumbered (was 6-12), step references updated throughout |
| `docs/enrichment_engine_plan_v2.md` | Architecture and engineering plan |
| `docs/enrichment_engine_changeset.md` | File-by-file disposition |
| `docs/engine_testing_guide.md` | This file |

### What was NOT touched

- `scripts/validate_intent.py` (still validates final output, exit 0/1/2)
- `scripts/build_confirmed_config.py`, `generate_schematic.py`, `generate_layout.py`, all DRC/LVS scripts
- `assets/device_info/IO_device_info_T28.json` and parser (still used by SKILL generators)
- `assets/core/layout/auto_filler.py`, `confirmed_config_builder.py`, layout generators
- `assets/layout_editor/*`, `assets/skill_code/*`
- `references/draft_builder_T28.md`, `wizard_T28.md`, `T28_Technology.md`, `skill_language_reference.md`

---

## 2. How to Run the Engine

### Prerequisites
Python 3.9+ available. The skill assumes a project-level `.venv`. On this system the bridge-Agent venv is at `C:\Users\90590\Desktop\bridge-Agent\.venv\Scripts\python.exe`.

### Basic invocation

```bash
cd c:/Users/90590/Desktop/bridge-Agent/io-ring-orchestrator-T28

../.venv/Scripts/python.exe scripts/enrich_intent.py \
  T28_Testbench/semantic_intents/IO_28nm_3x3_single_ring_analog.json \
  /tmp/out.json \
  T28
```

### Expected output (success path)

```
[>>] Enriching semantic intent...
   Input:    .../IO_28nm_3x3_single_ring_analog.json
   Output:   /tmp/out.json
   Trace:    /tmp/out.trace.json
   Wiring:   .../device_wiring_T28.json

[OK] Enrichment complete in 1-3ms
   Pads: 12, Corners: 4
   Wrote: /tmp/out.json
   Trace: /tmp/out.trace.json
```
Exit code: 0.

### End-to-end with downstream validation

```bash
../.venv/Scripts/python.exe scripts/enrich_intent.py SEMANTIC.json INTENT.json T28 \
  && ../.venv/Scripts/python.exe scripts/validate_intent.py INTENT.json
```

Both should exit 0 for any valid input.

---

## 3. What Has Been Verified (Smoke Tests)

| Scenario | Test fixture | Verified behavior |
|----------|--------------|-------------------|
| Pure analog, counterclockwise, single domain | `IO_28nm_3x3_single_ring_analog.json` | 12 pads + 4 corners (all PCORNERA_G), suffix correct, all pin labels match enrichment rules, validate_intent passes |
| Mixed analog+digital, counterclockwise | `IO_28nm_3x3_single_ring_mixed.json` | Digital providers self-named on primary pin, digital IO has direction, corners mix PCORNER_G (digital-digital) and PCORNERA_G (mixed/analog), validate_intent passes |
| Clockwise placement, 3x3 | (deleted after test) | Suffixes correct, 4 corners generated in clockwise order |
| Ring ESD active | (deleted after test) | All 12 pads have VSS = ESD signal name, trace reports `esd_pads_overridden: 12` |
| Error: device with `_H_G` suffix | (deleted after test) | Exit 1, message names position + suggested fix + section pointer |
| Error: domain reference not defined | (deleted after test) | Exit 1, lists available domains, suggests fix |
| Error: digital device in analog domain (kind mismatch) | (deleted after test) | Exit 1, includes "device/domain mismatch" hint |
| Error: missing direction on PDDW16SDGZ | (deleted after test) | Exit 1, points to §5.4 |
| Gate G3: 3 unique digital provider names instead of 4 | (deleted after test) | Exit 3, lists found names |
| Gate G4: VSS inconsistency from override | (deleted after test) | Exit 3, lists distinct VSS labels |
| Override: literal string | `right_0` TACVDD = literal | Override applied and recorded in trace |
| Override: `label_from:` reference | `right_0` TACVDD = `label_from:domain.vdd_provider` | Override resolved through engine machinery |

---

## 4. What to Test Next

### 4.1 High priority — Phase 0b (Generate semantic intents for goldens)

Only 2 of the 30 golden cases have semantic intents. Need to write the remaining 28 by hand from `T28_Testbench/golden_output/<case>/io_ring_intent_graph.json`. For each:

1. Read the golden `io_ring_intent_graph.json`
2. Read the test prompt `<case>.txt` for context
3. Reverse-engineer the semantic intent: extract device classes (without suffix), domain assignments, directions. Drop the engine-generated parts (corners, pin_connection).
4. Save to `T28_Testbench/semantic_intents/<case>.json`
5. Run engine, diff against golden semantically (not byte-exact — see §5)

The 30 cases by complexity (start with simpler):

| Group | Cases | Complexity |
|-------|-------|------------|
| Single-ring 3x3 / 4x4 / 5x5 / 6x6 / 7x7 | 14 cases | Easiest — single domain, no inner pads |
| Mixed 3x3 / 4x4 / 5x5 | (in above) | Multi-domain (analog + digital) |
| 8x8 double ring | 4 cases | Inner pads (positions like `top_2_3`) |
| 10x6, 12x12, 12x18, 18x12, 18x18 | ~12 cases | Multi-voltage-domain analog |
| 10x10 / 12x12 double-ring multi-domain | ~3 cases | Hardest |

**Recommended order:** Start with `IO_28nm_4x4_single_ring_analog`, `IO_28nm_4x4_single_ring_digital`, `IO_28nm_5x5_single_ring_mixed`. Get 5-10 simple cases working before tackling double rings or multi-voltage.

### 4.2 Medium priority — Build a regression diff harness

Write `tests/integration/test_goldens_engine.py`:

```python
# Pseudocode
def test_golden(case_name):
    # Load golden semantic intent
    semantic = load(f"T28_Testbench/semantic_intents/{case_name}.json")
    # Run engine
    engine_output = enrich(semantic, ...)
    # Load golden intent graph
    golden = load(f"T28_Testbench/golden_output/{case_name}/io_ring_intent_graph.json")
    # Semantic-equality compare
    assert_semantic_equal(engine_output, golden)
```

`assert_semantic_equal` should compare:
- Same set of pad instances (by `(name, position)` as key)
- Each pad has same `device`, same `direction` (if any), same set of `pin_connection` entries with same labels
- Same set of corner positions and devices (corner names and ordering may differ — this is OK)

NOT byte-exact diff — golden field ordering and corner naming conventions are inconsistent across the 30 cases (`CORNER_TL` vs `CORNER_TOPLEFT`, different placement orderings).

### 4.3 Medium priority — Unit tests

Create `tests/unit/test_enrichment_engine.py` covering:

- `parse_position`: pad, inner_pad, corner, malformed
- `suffix_for_side`: all 4 sides
- `_self_core`: bare name vs `<>` bus notation
- `ResolutionContext.resolve` for each `label_from` value
- `apply_ring_esd_override`: count of pads modified
- Each gate G1-G8 individually
- Wiring table validator: catches missing family, missing pins, unknown label_from

### 4.4 Lower priority — Real downstream test

Run the full pipeline end-to-end on one case:
1. Use a semantic intent to produce intent_graph.json (engine, Step 3)
2. Run validate_intent.py (Step 4)
3. Run build_confirmed_config.py with `--skip-editor` (Step 5)
4. Run generate_schematic.py and generate_layout.py (Step 6)
5. If a Virtuoso bridge is available, run Steps 7-10 (Virtuoso execution + DRC + LVS)
6. Compare output against golden_output/<case>/

This validates that the engine output is fully compatible with the existing downstream pipeline.

---

## 5. Known Issues & Limitations

### Confirmed bugs / limitations

| # | Issue | Severity | Workaround |
|---|-------|----------|------------|
| 1 | Gate G3 counts unique values across `domains.<id>.{low_vdd, low_vss, high_vdd, high_vss}` keys, not actual digital pad classifications. Won't catch the case where the AI puts 5 pads with 5 different signal names through `PVDD1DGZ`/etc. | Medium | Future: gate should also count unique signal names from instances with digital_power_* / digital_ground_* family |
| 2 | Pin overrides for pins that don't exist on the device are silently ignored | Low | Document; future: warn |
| 3 | If a non-digital-IO instance has `direction` set, it's silently dropped from output | Low | Document; future: warn |
| 4 | Wiring uses both `global.vss_ground` and `domain.low_vss` for what resolves to the same value (e.g. PVDD2POC.VSS uses `global.vss_ground` while rules say "low voltage domain ground signal name"). Functionally equivalent but conceptually inconsistent | Low | Cosmetic; pick one in a future revision |
| 5 | Corner ordering in engine output is fixed (`bottom_left, top_left, top_right, bottom_right` for counterclockwise; `top_right, bottom_right, bottom_left, top_left` for clockwise). Goldens vary — diffs in corner ordering are NOT engine bugs | N/A | Use semantic-equality diff |
| 6 | Field order in pad output is `name, position, type, device, [direction], pin_connection`. Some goldens use `name, device, position, type, ...`. Not a bug; cosmetic | N/A | Use semantic-equality diff |
| 7 | Engine doesn't validate `tech_node` field in semantic intent (CLI does, weakly) | Low | Pass tech_node correctly to CLI |
| 8 | Engine doesn't cross-check pin names against `IO_device_info_T28.json` PDK templates at load time | Medium | Consider adding to wiring validation |

### Hazards (not bugs but worth knowing)

- **Wiring table review needed.** I (the implementing agent) caught two bugs in the wiring table during planning (PVSS1AC and PVSS1A consumer TACVSS/TAVSS were `self`, fixed to `domain.vss_provider`). These were found by re-reading the rules carefully. **A T28 designer should review the wiring table line-by-line before production use** to ensure no other latent bugs.
- **`emit: false` pins.** POC and digital IO non-power pins (PAD/REN/OEN/C/I) are defined in the wiring table but NOT emitted to the output, matching today's golden format. If the downstream SKILL generator ever needs these in intent_graph, flip `emit` to `true` — the engine has the data ready.
- **ESD override applies to ALL pads including digital providers.** When ring ESD is active, even PVSS1DGZ's VSS pin gets overridden to the ESD signal (correctly — rule says every pad). Verify with downstream LVS that this is correct in real designs.

---

## 6. How to File a Bug

When you find a bug:

1. **Capture the input** — copy the semantic intent JSON to `T28_Testbench/bug_repros/<short_name>.json`
2. **Capture the engine output** — both stderr (the error message) and the trace JSON if generated
3. **Capture the expected behavior** — quote from `enrichment_rules_T28.md` or the golden output
4. **File** as a comment / issue with all three

Example:
> **Bug**: Pin override on non-existent pin silently ignored
> **Input**: `T28_Testbench/bug_repros/override_nonexistent_pin.json` — overrides `"FAKEPIN": "X"` on a PDB3AC instance
> **Engine output**: Exit 0, output instance has no FAKEPIN entry, trace doesn't list FAKEPIN in `overrides_applied`
> **Expected**: Engine should warn or error that FAKEPIN doesn't exist on PDB3AC

---

## 7. Reference Map

When debugging, here are the files you'll likely consult:

| Question | File |
|----------|------|
| "What does the AI's semantic intent look like?" | `references/enrichment_rules_T28.md` §4 |
| "Why did the AI choose PVDD3AC vs PVDD3A?" | `references/enrichment_rules_T28.md` §5.5, §5.6 |
| "What pin connects to what for device X?" | `assets/device_info/device_wiring_T28.json` |
| "What does engine error code N mean?" | `references/enrichment_rules_T28.md` §6.3 |
| "What's the engine's algorithm?" | `assets/core/layout/enrichment_engine.py` (top docstring + phase comments) |
| "What's the architecture rationale?" | `docs/enrichment_engine_plan_v2.md` |
| "What changed and what didn't?" | `docs/enrichment_engine_changeset.md` |

---

## 8. Quick Sanity Check (5 Minutes)

To confirm the engine works on this machine before deeper testing:

```bash
cd c:/Users/90590/Desktop/bridge-Agent/io-ring-orchestrator-T28
PY=../.venv/Scripts/python.exe

# Test 1: happy path on 3x3 analog
$PY scripts/enrich_intent.py \
  T28_Testbench/semantic_intents/IO_28nm_3x3_single_ring_analog.json \
  /tmp/sanity_analog.json T28
# Expect: exit 0, "Pads: 12, Corners: 4"

# Test 2: happy path on 3x3 mixed
$PY scripts/enrich_intent.py \
  T28_Testbench/semantic_intents/IO_28nm_3x3_single_ring_mixed.json \
  /tmp/sanity_mixed.json T28
# Expect: exit 0, "Pads: 12, Corners: 4"

# Test 3: validate downstream-compatible
$PY scripts/validate_intent.py /tmp/sanity_analog.json
$PY scripts/validate_intent.py /tmp/sanity_mixed.json
# Expect: both "Configuration validation passed", exit 0

# Cleanup
rm -f /tmp/sanity_*.json /tmp/sanity_*.trace.json
```

If all three pass, the engine is operational. If any fails, the engine is broken on this machine — investigate before further testing.

---

## 9. Open Questions for User

These need user decisions before production rollout (from v2 plan):

1. **Domain expert** for wiring table line-by-line review (Phase 0a) — who?
2. **Compare-mode duration** during rollout — 2 weeks default
3. **Compare-mode canonical output** when engine and legacy disagree — legacy (safety) by default
4. **Pin override availability** in production — currently allowed; could restrict to debug-only
5. **Trace log retention** — currently no cleanup; suggest 30 days
6. **Step 4 (validate_intent.py) fate** — keep as redundant safety net or remove? Currently kept.

---

## 10. What's Explicitly Out of Scope (For This Round)

- T180 support (engine is T28-only; CLI rejects other nodes)
- Compare mode (`AMS_ENGINE_MODE=compare`) plumbing — not implemented yet
- Migration guide doc — not written yet
- Unit test suite — not written yet
- Integration test harness — not written yet
- 28 of 30 golden semantic intents — not written yet

These are the next-up items. The engine, wiring, CLI, and documentation foundation are in place; building tests and migrating the workflow are the next phase of work.
