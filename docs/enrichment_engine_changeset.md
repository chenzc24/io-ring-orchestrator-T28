# Enrichment Engine — Explicit Changeset (Revised)

Companion to `enrichment_engine_plan_v2.md`. Enumerates every file created, modified, or kept untouched, and every section of `enrichment_rules_T28.md` that stays vs moves out — preserving the existing style (concise SKILL.md, detailed reference).

**Revision note:** Earlier draft proposed two new reference files (`semantic_intent_T28.md`, `enrichment_engine_T28.md`). On review, those were merged into the existing `enrichment_rules_T28.md` to avoid file sprawl, reduce token load, and keep the AI's reading path single-file. See §6 for trade-offs.

---

## Style Contract (Preserved)

| Layer | Role | Style |
|-------|------|-------|
| `SKILL.md` | Workflow orchestration | Concise. Bash commands, brief explanations. AI consults `references/` for rules. |
| `references/*.md` | Detailed rules consulted by AI | Verbose. Examples, JSON snippets, edge cases. |
| Asset code/JSON | Mechanical execution | Hidden from AI; consumed by engine. |

---

## 1. File-by-File Changeset

### 1.1 Created Files

| Path | Type | Purpose | Approx size |
|------|------|---------|-------------|
| `assets/core/layout/enrichment_engine.py` | Code | Core engine: load wiring, expand instances, generate corners, run gates, ESD override | ~350 lines |
| `assets/device_info/device_wiring_T28.json` | Data | Device → pin semantic-source mapping | ~250 lines |
| `scripts/enrich_intent.py` | Code | CLI wrapper: `enrich_intent.py semantic.json intent_graph.json T28` | ~80 lines |
| `tests/unit/test_enrichment_engine.py` | Test | Unit tests for engine logic | ~600 lines |
| `tests/integration/test_goldens_engine.py` | Test | 30 golden-case integration tests | ~100 lines |
| `T28_Testbench/semantic_intents/<case>.json` × 30 | Test data | Phase 0b output: golden semantic intents | 30 files, ~50 lines each |
| `docs/enrichment_engine_plan_v2.md` | Doc | Engineering plan (already created) | (exists) |
| `docs/enrichment_engine_changeset.md` | Doc | This file | (this file) |
| `docs/migration_guide.md` | Doc | Operator's guide: `AMS_ENGINE_MODE` flag, compare mode, rollback | ~150 lines |

**No new reference files.** All AI-facing documentation merged into `enrichment_rules_T28.md`.

### 1.2 Modified Files

| Path | Change | Lines affected |
|------|--------|----------------|
| `SKILL.md` | Steps 3-5 rewritten (concise); Step 4 deleted | ~50 lines replaced with ~40 lines |
| `references/enrichment_rules_T28.md` | **Restructured** — semantic decisions kept, mechanical rules removed, output format and engine interaction sections added | ~700 lines → ~400 lines |
| `scripts/build_confirmed_config.py` | Add `--from-semantic` flag for compare-mode plumbing (optional) | ~10 lines added |

### 1.3 Untouched Files

| Path | Why untouched |
|------|---------------|
| `assets/device_info/IO_device_info_T28.json` | Still used by SKILL generators for physical pin coordinates |
| `assets/device_info/IO_device_info_T28_parser.py` | Still used by SKILL generators |
| `scripts/validate_intent.py` | Same input/output format |
| `scripts/generate_schematic.py`, `generate_layout.py` | Consume confirmed.json same as today |
| `scripts/check_virtuoso_connection.py`, `run_il_with_screenshot.py`, `run_drc.py`, `run_lvs.py`, `run_pex.py` | Unrelated |
| `assets/core/layout/auto_filler.py` | Filler insertion still in Step 6 |
| `assets/core/layout/confirmed_config_builder.py` | Editor flow unchanged |
| `assets/core/layout/layout_generator.py` and friends | Layout generation unchanged |
| `assets/core/schematic/schematic_generator_T28.py` | Schematic generation unchanged |
| `assets/layout_editor/*` | Editor unchanged |
| `references/draft_builder_T28.md` | Step 2 (draft) is structural-only, unchanged |
| `references/wizard_T28.md` | Wizard contract unchanged; runs before semantic intent generation |
| `references/T28_Technology.md`, `skill_language_reference.md`, `image_vision_instruction.md` | Unrelated |
| `T28_Testbench/IO_28nm_*.txt` | User prompt fixtures unchanged |
| `T28_Testbench/golden_output/<case>/*` | Golden outputs unchanged (engine must reproduce them) |

---

## 2. `enrichment_rules_T28.md` — Restructured (Single Merged File)

### 2.1 Final Structure (~400 lines)

```
1. Universal Ring Structure Principle              (~10 lines)
2. User Intent Priority                             (~10 lines)
3. On-Demand Clarification Trigger                  (~15 lines)
4. [NEW] Output Format: Semantic Intent JSON       (~80 lines)
   4.1 Schema table (every field, type, constraint)
   4.2 Mixed-signal example
   4.3 Multi-domain example
   4.4 Hard rules (engine will reject)
5. G1: Classification Rules                         (~250 lines)
   5.1 Step 1: Signal classification (analog vs digital)
   5.2 Step 2.1: Digital continuity & context re-classification
   5.3 Step 2.2: Digital provider count = 4 unique names (semantic only)
   5.4 Step 2.3: Direction inference rules
   5.5 Step 3.1: Voltage domain judgment + family choice (3AC vs 3A)
   5.6 Step 3.2: Provider vs consumer device class selection (1AC↔3AC, 1A↔3A)
   5.7 Step 4: Ring ESD trigger conditions
6. [NEW] Engine Interaction                         (~40 lines)
   6.1 Invocation (one bash command)
   6.2 Override syntax (literal vs label_from: prefix)
   6.3 Common engine errors and how to fix
```

### 2.2 Sections that STAY

| Section | Why it stays | Modifications |
|---------|--------------|---------------|
| Universal Ring Structure Principle | AI's domain continuity reasoning | None |
| User Intent Priority | How AI prioritizes user prompt over inference | None |
| On-Demand Clarification Trigger | When AI invokes wizard | Item 1 reworded: drop "pin family" ambiguity (engine handles pins) |
| **G1 Step 1**: Signal classification | Analog vs digital decision | None |
| **G1 Step 2.1**: Digital continuity & context | Re-classification when digital signals appear in analog blocks | None |
| **G1 Step 2.2** (semantic only) | Provider count = 4, naming | **Remove** "Digital Power/Ground Pin connection" subsection |
| **G1 Step 2.3** (direction part only) | Direction inference (RST→input, D0→output) | **Remove** "Digital IO Pin Connection" tables and "All Digital Pads Must Have 4 Pin Connections" |
| **G1 Step 3.1**: Voltage Domain Judgment | Provider selection within domain, 3AC vs 3A choice | None — keep all |
| **G1 Step 3.2** (semantic only) | Consumer family must match provider family | **Remove** all "Required Pins" subsections |
| **G1 Step 3.3** (semantic only) | Analog IO device class (PDB3AC) | **Remove** TACVSS/TACVDD pin mechanics |
| **G1 Step 4** (semantic only) | When to declare Ring ESD, device class by domain | **Remove** "Ring-wide VSS pin override" mechanics, "PVSS2A Required Pins" |

### 2.3 Sections that MOVE OUT (mechanical → engine)

| Section being removed | New home |
|-----------------------|----------|
| Step 2.2 "Digital Power/Ground Pin connection" tables (PVSS1DGZ/PVDD1DGZ/PVDD2POC/PVSS2DGZ pin → label maps) | `device_wiring_T28.json` |
| Step 2.3 "Digital IO Pin Connection" (PDDW16SDGZ/PRUW08SDGZ pin maps + REN/OEN direction rules) | `device_wiring_T28.json` (`io_direction_rules`) |
| Step 2.3 "All Digital Domain Pads Must Have 4 Pin Connections" | Engine gate G5 |
| Step 2.3 "VSS Pin Consistency" mechanical rule | Engine gate G4 |
| Step 3.2 "Required Pins" tables (8 device types) | `device_wiring_T28.json` |
| Step 3.3 "TACVSS/TACVDD pin connection" mechanical rule | `device_wiring_T28.json` (PDB3AC entry) |
| Step 3.4 entire "Corner Devices Classification" section | Engine Phase 3 |
| Step 4 "Ring-wide VSS pin override" | Engine Phase 4 (ESD override) |
| Step 4 "PVSS2A Required Pins" | `device_wiring_T28.json` (PVSS2A entry) |
| Device suffix rule "_H_G for left/right, _V_G for top/bottom" | Engine Phase 2 |
| `_CORE` suffix rule for provider AVDD/AVSS | `device_wiring_T28.json` (`label_from: self_core`) |
| **G2 entire section** "Generate Intent Graph JSON" (15 JSON examples per device type) | **Replaced** by §4 Output Format (1 small example) |
| Task Completion Checklist items about pin connections | Replaced by gate-pass requirement |

### 2.4 New Sections Added

#### §4 Output Format: Semantic Intent JSON (~80 lines)

Format reference for the AI's output. Replaces the old G2 "Generate Intent Graph JSON" section, but for the much smaller semantic intent format.

Outline:
- Top-level schema table (every field with type and constraint)
- One mixed-signal example (1 analog domain, 1 digital domain, 1 inner pad)
- Hard rules: device must NOT include `_H_G`/`_V_G`; direction required for digital_io devices; all `instance.domain` values must exist in `domains{}`; inner pad position requires idx1<idx2; do NOT include corners (engine generates).
- Position-Indexed Identity rule (same name allowed at multiple positions, processed independently).
- Constraint precedence: user prompt > Draft Editor hints > wizard_constraints > AI inference.

#### §6 Engine Interaction (~40 lines)

Brief reference for engine usage. Replaces what would have been a separate `enrichment_engine_T28.md`.

Outline:
- **Invocation**: bash command with input/output paths and tech node
- **Override syntax**: `"VSS": "MY_NET"` (literal) vs `"VSS": "label_from:domain.vss_provider"` (reference)
- **Common errors**:
  - "Device not in wiring table" → check device name spelling, no suffix
  - "Domain reference not found" → check domain ID matches `domains{}` key
  - "Provider count != 4" → re-classify suspect signal as analog
  - "Domain continuity warning" → may be intentional, review trace log

The engine itself emits rich error messages (see §3.2) so this section is small.

### 2.5 Net Change to `enrichment_rules_T28.md`

| Metric | Before | After |
|--------|--------|-------|
| Total lines | ~700 | ~400 |
| Pin connection tables | 14 device types × tables | 0 |
| Code/JSON examples | ~15 large examples | ~3 (semantic intent: minimal, multi-domain, override) |
| Tokens consumed when AI loads | ~17K | ~10-11K |

---

## 3. Engine — Self-Documenting Error Messages

Replaces the deleted `enrichment_engine_T28.md` reference. Engine errors include rule, position, suggestion, and pointer to enrichment_rules section.

### 3.1 Format Template

```
[ENGINE-<class>] <gate_id> <one-line summary>
  At: <position> (<device>, domain=<domain>)
  Detail: <what the engine found>
  Hint: <suggested fix in semantic intent>
  See: references/enrichment_rules_T28.md §<section>
```

### 3.2 Examples

```
[ENGINE-GATE] G3: Digital provider count is 5, expected exactly 4 unique names
  At: top_3 (device=PVDD1DGZ, domain=dig_1)
  Detail: providers found = {VIOL, GIOL, VIOH, GIOH, EXTRA_VDD}; "EXTRA_VDD" is the unexpected fifth
  Hint: "EXTRA_VDD" likely belongs to an analog voltage domain. Re-classify it as analog
        (assign to an analog domain, change device to PVDD1AC or PVDD1A) in semantic intent.
  See: enrichment_rules_T28.md §5.3 (Step 2.2 Digital provider count rule)

[ENGINE-INPUT] Device name includes suffix
  At: left_5 (device=PDB3AC_H_G)
  Detail: semantic intent must use base device names; engine adds _H_G or _V_G from position
  Hint: Change "device": "PDB3AC_H_G" to "device": "PDB3AC"
  See: enrichment_rules_T28.md §4.4 (Hard rules)

[ENGINE-INPUT] Domain reference not found
  At: left_2 (domain=ana_2)
  Detail: instance references domain "ana_2" but it is not defined in semantic_intent.domains
  Hint: Add ana_2 to domains{}, or change this instance's domain to one that exists
  See: enrichment_rules_T28.md §4.1 (Schema)

[ENGINE-WARN] G8: Domain continuity — analog domain "ana_1" has 2 non-contiguous blocks
  Block 1: positions left_0..left_4
  Block 2: positions bottom_2..bottom_5
  Each block has its own provider pair, so this is allowed. Verify intentional.
  See: enrichment_rules_T28.md §5.5 (Step 3.1)
```

These messages teach the AI how to fix issues without needing a separate behavioral reference.

---

## 4. SKILL.md — Step 3 Rewrite (Concise Style, Single Reference)

### After

```markdown
### Step 3: Generate Semantic Intent + Run Enrichment Engine

Reference: `references/enrichment_rules_T28.md` (classification rules, output format, override syntax — all in one file).

**Mandatory inputs:**
- Step 2 draft JSON (structural source — immutable)
- Step 2b draft editor output (if opened — device hints carried through)
- Original user prompt (voltage-domain assignment, provider naming, direction overrides, ring ESD declaration)
- `wizard_constraints` (only if wizard ran)

**Input precedence:**
1. Explicit user prompt constraints
2. Draft Editor `device` hints
3. `wizard_constraints`
4. Default classification inference

**Process:**
1. Per `enrichment_rules_T28.md` §5, decide: signal class, device, domain assignment, provider names, direction, ring ESD.
2. Write `{output_dir}/io_ring_semantic_intent.json` per `enrichment_rules_T28.md` §4 schema.
3. Run engine:

```bash
$AMS_PYTHON $SCRIPTS_PATH/enrich_intent.py \
  {output_dir}/io_ring_semantic_intent.json \
  {output_dir}/io_ring_intent_graph.json \
  T28
```

- Exit 0 → engine wrote `io_ring_intent_graph.json` + `enrichment_trace.json`. Proceed to Step 4.
- Exit 1 → semantic intent error. Read engine stderr, fix per its hint, re-run.
- Exit 2 → wiring/engine bug. Stop and report.
- Exit 3 → gate failure. Read engine stderr, fix classification in semantic intent, re-run.

**Handoff rule:** Treat draft structural fields (`ring_config`, `name`, `position`, `type`) as immutable.

### Step 4: Validate JSON

```bash
$AMS_PYTHON $SCRIPTS_PATH/validate_intent.py {output_dir}/io_ring_intent_graph.json
```

- Exit 0 → proceed to Step 5.
- Exit 1 → engine produced invalid output (should not happen — report as engine bug).
- Exit 2 → file not found.
```

**Step renumbering:** Old Step 4 (gate check) deleted — engine handles gates. Old Step 5 (validate) becomes new Step 4. Old Step 6 (confirmed config) becomes new Step 5. Etc. SKILL.md Step IDs shift down by one from old Step 6 onward.

---

## 5. Token / Cost Comparison

### Per-run AI token cost

| State | Tokens loaded for Step 3 | Tokens generated | Repair iterations | Total per typical run |
|-------|--------------------------|------------------|-------------------|------------------------|
| Today | ~17K | ~5K | 1-2 (each ~22K) | ~40-80K |
| v2 plan (3 files) | ~22K | ~1K | 0 | ~23K |
| **Merged (this revision)** | **~10-11K** | **~1K** | **0** | **~12K** |

The merge cuts per-run cost by **~70%** vs today and **~50%** vs the 3-file v2 plan.

### Per-run latency

| State | AI inference time | Engine time | Total enrichment |
|-------|-------------------|-------------|-------------------|
| Today | ~30-60s | n/a | ~30-60s |
| **Merged (this revision)** | ~10-15s (smaller output) | <1s | ~10-15s |

---

## 6. Trade-offs of the Merge

### What we lose

- One bigger file (~400 lines) is harder to navigate than two ~200-line files. Mitigated by clear section numbering.
- Mixing classification rules with output format and engine interaction blurs the document's purpose slightly. Mitigated by §4 and §6 being clearly demarcated.

### What we gain

- One file load instead of three.
- Format examples sit next to the rules that produce them.
- ~6-7K tokens saved per run vs current.
- ~11K tokens saved per run vs the 3-file v2 plan.
- Less repository sprawl; one source of truth for AI enrichment guidance.
- SKILL.md Step 3 references one file instead of three.

**Net win.**

---

## 7. Pre-Implementation Decision Points

| Decision | Default suggestion |
|----------|---------------------|
| Domain expert for wiring table review (Phase 0a) | (please assign) |
| Compare-mode duration | 2 weeks |
| Compare-mode canonical output (when engine and legacy disagree) | legacy (safety) |
| Pin override availability in production | Yes (escape hatch needed for novel PDK devices) |
| Trace log retention | 30 days |
| Step 4 (gate check) fate after engine ships | Remove (engine guarantees gates) |

---

## 8. Summary of Revisions to v2 Plan

| Concern | v2 plan | This changeset (revised) |
|---------|---------|--------------------------|
| New reference files | 2 (`semantic_intent_T28.md`, `enrichment_engine_T28.md`) | **0 — merged into `enrichment_rules_T28.md`** |
| Reference token load per run | ~22K | **~10-11K** |
| Engine error messages | Plain | **Self-documenting with §-pointers** |
| `enrichment_rules_T28.md` final size | ~350 lines | **~400 lines (with merged sections)** |
| SKILL.md Step 3 references | 3 files | **1 file** |
| Net repository changes (excluding tests/data) | +5 files, -0 deleted | **+3 files, -0 deleted** |

The architectural direction from v2 is unchanged: hybrid AI/code split with the device name as handoff. This revision tightens the documentation footprint without losing any functionality.
