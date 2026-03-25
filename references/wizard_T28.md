# IO Ring Wizard — T28 Reference

This file defines the full specification for the interactive wizard (Step 0.8) in the T28 IO Ring generation workflow. The wizard uses a combination of plain text output and `AskUserQuestion` UI calls to efficiently collect user intent before draft building begins.

---

## Design Principles

1. **Auto-classify first, ask only about ambiguous signals** — never ask the user to confirm what the AI can determine with high confidence from the signal name alone
2. **Use plain text for displaying lists and tables** — `AskUserQuestion` preview panes are only visible when an option is actively focused; do NOT use them to display full signal tables or multi-signal information
3. **Reserve `AskUserQuestion` for binary or small-set decisions** — provider vs consumer, domain count, direction of one signal; never for reviewing lists
4. **Print, then ask** — always print the current state as markdown text in the conversation before calling `AskUserQuestion` for confirmation or correction

---

## Trigger Conditions

Use a two-stage trigger model.

### Stage A: Eligibility

Wizard is **eligible** only when ALL of the following are true:

1. User provided a signal list in their prompt
2. Prompt does NOT contain any explicit constraint indicators:
  - Device type keywords: `PDB3AC`, `PVDD3AC`, `PVSS3AC`, `PVDD1AC`, `PVSS1AC`, `PDDW16SDGZ`, `PVDD1DGZ`, `PVSS1DGZ`, `PVDD2POC`, `PVSS2DGZ`, `PVDD3A`, `PVSS3A`
  - Domain language: `voltage domain`, `domain`, `provider`, `consumer`
  - Explicit per-signal direction assignments: `input`, `output`

Wizard is **not eligible** when any of the following are true:

- Prompt already contains explicit specifications → skip Step 0.8 and treat as Priority 1 directly
- User provides draft/final intent graph input (skip to Step 2/3)
- User explicitly says "auto", "skip wizard", or "no wizard"

### Stage B: User Opt-In

If wizard is eligible, ask user whether to run wizard mode.

- Run wizard only if user explicitly chooses to enter wizard.
- Otherwise, skip wizard and continue directly to Step 1 (default behavior).

---

## Wizard Phases Overview

| Phase | Name | Text output | UI calls |
|-------|------|------------|----------|
| G | Geometry | — | 2 calls (placement + dimensions) |
| W1 | Signal Classification | Draft table, then corrected table | ⌈N_ambiguous/4⌉ calls per batch + 1 confirm |
| W2 | Voltage Domain Grouping | Proposed domain ranges | 1–3 calls depending on domain count |
| W3 | Digital Domain Providers | Proposed provider mapping | 1 call |
| W4 | Signal Directions | Proposed directions | Only for ambiguous directions |
| W5 | Final Confirmation | Complete plan table | 1 confirm call |

**Phase G runs first, before W1.** Geometry answers (placement order, starting side, starting signal, dimensions) feed into Step 1 (draft builder). Signal phases W1–W5 feed into Step 2 (enrichment).

---

## Phase G — Geometry

Runs before signal classification. Collects ring structure: traversal direction, starting side, starting signal, and pad counts. Output feeds directly into Step 1 (draft builder).

### Call G1 — Placement Order + Starting Side (2 questions, 1 UI call)

```
Q1: "Ring traversal direction?"
  A: Clockwise      — top → right → bottom → left
  B: Counterclockwise — left → bottom → right → top

Q2: "Which side is first in your signal list?"
  A: Top      B: Right      C: Bottom      D: Left
```

**Example**: user selects Clockwise + Top → the ring traversal is top→right→bottom→left, and signal list position 0 maps to `top_0`.

### Call G2 — Dimensions (1 question, 1 UI call)

Before calling, compute `auto_n = total_signal_count / 4`.

**If total signal count is divisible by 4** (equal square ring possible):

```
Q: "Pads per side?"
  A: "{auto_n} per side — equal square ring  (auto: {total} ÷ 4 = {auto_n})  [Recommended]"
  B: "Custom — I'll specify each side separately"   [Other → "top=X right=Y bottom=X left=Y"]
```

**If total signal count is NOT divisible by 4** (cannot form a square ring):

```
Q: "Ring dimensions? ({total} signals cannot form an equal square ring)"
  A: "I'll type the pad counts"   [Other → "top=X right=Y bottom=X left=Y"]
  B: "top={a} right={b} bottom={a} left={b}"   [AI suggests the nearest symmetric split]
```

### Geometry Output

Produces a `geometry` object passed to Step 1:

```
geometry = {
  "placement_order": "clockwise" | "counterclockwise",
  "starting_side":   "top" | "right" | "bottom" | "left",
  "width":           N,    // top/bottom pad count
  "height":          M     // left/right pad count
}
```

**Starting signal** does not need to be asked — it is always signal list position 0. The `starting_side` tells Step 1 where position 0 maps in the ring.

### Example — 48 signals, clockwise, top start

User answers: Clockwise + Top, then "12 per side (auto: 48÷4=12)".

```
geometry = {
  "placement_order": "clockwise",
  "starting_side":   "top",
  "width":  12,
  "height": 12
}
```

Signal list position 0 (D4) → `top_0`.
Signal list position 11 (SLP) → `top_11`.
Signal list position 12 (VREFDES2) → `right_0`.
... etc.

### Inner Pad Insertions

**Out of scope for wizard.** Inner pad insertions (double-ring) must be specified in text as before. If the user's prompt already contains inner pad descriptions, they are preserved and passed to Step 1 unchanged alongside the `geometry` output.

---

## Phase W1 — Signal Classification

### Core Principle: Auto-Classify Tier 1 Silently, Ask Only About Tier 2

Only ambiguous (Tier 2) signals are presented via UI — one signal per question, up to 4 questions per call.

---

### Step W1-A: Auto-Classify All Signals (Silent)

Auto-classify every signal by name pattern. Assign to **Tier 1 (high confidence, no UI)** or **Tier 2 (ambiguous, needs UI)**.

#### Tier 1 — Auto-Classify, No UI

| Pattern | Auto-classification |
|---------|---------------------|
| `RST`, `RSTN`, `RESET` | Digital IO — input |
| `SCK`, `SCLK` | Digital IO — input |
| `SDI`, `MOSI` | Digital IO — input |
| `SDO`, `MISO` | Digital IO — output |
| `D[0-9]+`, `DA[0-9]+`, `DB[0-9]+` | Digital IO — output |
| `SLP`, `SLEEP` | Digital IO — input |
| `SYNC`, `CS`, `CSN`, `EN`, `ENB` | Digital IO — input |
| `IOV*` (IOVDDH, IOVSS, IOVDDL) | Digital provider — map by name suffix |
| `VCM`, `VINCM` | Analog IO |
| `CLKP`, `CLKN`, `CLKINN`, `CLKINP` | Analog IO |
| `VINN`, `VINP`, `VIN*` | Analog IO |
| `VAMP`, `VOUT*` | Analog IO |
| `IB*`, `IBIAS*`, `IBUF*` | Analog IO |
| `VREF*`, `REFIN`, `IBVREF`, `IBIAS_REF` | Analog IO |

#### Tier 2 — Ambiguous, Group for UI

| Ambiguity group | Examples | Default prediction |
|----------------|----------|--------------------|
| VDD-named (multiple present) | `AVDD`, `DVDD`, `CKVDD`, `RVDD` | Analog Power Provider |
| VSS-named (multiple present) | `AVSS`, `DVSS`, `CKVSS`, `RVSS` | Analog Ground Provider |
| Sub-block power/ground | `AVDDBUF`, `CBVDD`, `RVDDH` | Analog Consumer |
| `VSS` alone | `VSS` | Digital Ground Low |
| `DVSS`, `DVDD` | `DVSS`, `DVDD` | Ambiguous — explicit choice |
| Unknown patterns | anything else | Analog IO |

---

### Step W1-B: Print Two-Section Classification (Text Output)

Print in the conversation (never in AskUserQuestion preview):

```
Auto-classification (no action needed):
  Digital IO input  : RSTN  SCK  SDI  SLP
  Digital IO output : SDO  D0  D1  D2  D3  D4  D5  D6  D7  D8
  Digital providers : IOVDDH → PVDD2POC   IOVSS → PVSS2DGZ   IOVDDL → PVDD1DGZ
  Analog IO         : VCM  VINN  VINP  IBIAS3N  IBIAS2N  IBIAS1P  VAMP
                      IBUF1P  IBUF2N  IBUF3N  IBVREF  CLKINN  CLKINP
                      REFIN  IBIAS_REF  IBIAS  IBIAS2

Needs your confirmation (grouped by predicted type):
  Likely Power Providers : AVDD  DVDD  CKVDD  RVDD
  Likely Ground Providers: AVSS  DVSS  CKVSS  RVSS
  Likely Consumers       : VCALB  VCALF  AVDDBUF  CBVDD  RVDDH
  Ambiguous              : VSS
```

---

### Step W1-C: AskUserQuestion — One Signal per Question

For each batch of up to 4 Tier 2 signals, call `AskUserQuestion` with one question per signal. AI sets the recommended option first based on name-pattern prediction.

**Example — 4 ambiguous signals in one call:**

```
Q1: "AVDD — signal type?"
  Options:
    A: Analog Power Provider (PVDD3AC)   [Recommended]
    B: Analog Consumer (PVDD1AC)
    C: Analog IO (PDB3AC)
    D: Digital Power

Q2: "AVSS — signal type?"
  Options:
    A: Analog Ground Provider (PVSS3AC)  [Recommended]
    B: Analog Consumer (PVSS1AC)
    C: Analog IO (PDB3AC)
    D: Digital Ground

Q3: "AVDDBUF — signal type?"
  Options:
    A: Analog Consumer (PVDD1AC)         [Recommended]
    B: Analog Power Provider (PVDD3AC)
    C: Analog IO (PDB3AC)
    D: Digital Power

Q4: "VSS — signal type?"
  Options:
    A: Digital Ground Low (PVSS1DGZ)     [Recommended]
    B: Digital Ground High (PVSS2DGZ)
    C: Analog Consumer (PVSS1AC)
    D: Analog Provider (PVSS3AC)
```

For N Tier 2 signals → ⌈N/4⌉ sequential calls.

---

### Step W1-D: Print Updated Classification (Text Output)

After answers collected, print the complete corrected table in the conversation.

---

### Step W1-E: Single Confirm Call

```
question: "Signal classification looks correct?"
options:
  A: "Yes — proceed to domain setup"   [Recommended]
  B: "Fix one signal — I'll type name and new type"   [Other]
  C: "Restart classification"
```

---

### W1 Call Budget

| Scenario | UI calls |
|----------|---------|
| All signals Tier 1 (no ambiguity) | 0 + 1 confirm = **1 call** |
| 4 ambiguous signals | 1 + 1 confirm = **2 calls** |
| 8 ambiguous signals | 2 + 1 confirm = **3 calls** |
| 48-signal test case (~14 ambiguous) | 4 + 1 confirm = **5 calls** |

---

## Phase W2 — Voltage Domain Grouping

### Step W2-A: Auto-Detect Domains (Silent)

Count distinct VDD-provider/VSS-provider pairs from Phase W1 results. Propose groupings by signal proximity in the list (contiguous blocks around each provider pair).

### Step W2-B: Print Proposed Domains (Text Output)

Print as markdown in the conversation:

```
Detected N analog voltage domain(s):

  Domain 1  DVDD / DVSS  — covers indices 18–26
    DVSS DVDD VCALB VCALF IBIAS3N IBIAS2N VAMP IBIAS1P VCM
    Provider device type: PVDD3AC / PVSS3AC

  Domain 2  AVDD / AVSS  — covers indices 27–36
    AVDD AVSS VINN VINP AVDDBUF IBUF1P IBUF2N IBUF3N IBVREF CBVDD
    Provider device type: PVDD3AC / PVSS3AC
  ...
```

### Step W2-C: Confirm Grouping (UI Call)

**If 1 domain detected:**
```
question: "1 analog voltage domain detected. Confirm?"
options:
  A: "Correct — proceed"  [Recommended]
  B: "Split into multiple domains"
  C: "I'll specify manually"
```

**If 2–4 domains detected:**
```
question: "N domains detected (see table above). Confirm this grouping?"
options:
  A: "Correct — use this grouping"  [Recommended]
  B: "Merge some domains"
  C: "Change a domain boundary"  [Other — type: "Domain 2 ends at AVSS not CBVDD"]
  D: "I'll specify all ranges manually"
```

**If domain boundary is ambiguous (a signal could belong to either adjacent domain):**
Follow-up call showing the ambiguous signal and both options.

### Step W2-D: Per-Domain Device Type (UI Call — only if any domain confirmed)

After domain grouping is confirmed, ask about device type for each domain. Batch up to 4 domains per call.

```
Q1: "Domain 1 (DVDD/DVSS) — provider device type?"
  A: PVDD3AC / PVSS3AC  — standard (TACVDD/TACVSS pins)  [Recommended]
  B: PVDD3A  / PVSS3A   — use only if explicitly required (TAVDD/TAVSS pins)

Q2: "Domain 2 (AVDD/AVSS) — provider device type?"
  A: PVDD3AC / PVSS3AC  [Recommended]
  B: PVDD3A  / PVSS3A

Q3: "Domain 3 (CKVDD/CKVSS) — provider device type?"
  A: PVDD3AC / PVSS3AC  [Recommended]
  B: PVDD3A  / PVSS3A

Q4: "Domain 4 (RVDD/RVSS) — provider device type?"
  A: PVDD3AC / PVSS3AC  [Recommended]
  B: PVDD3A  / PVSS3A
```

**Skip this call** if all domains use the default PVDD3AC/PVSS3AC (i.e., no domain was flagged as needing PVDD3A). Only ask when at least one domain is ambiguous or the design note mentions "PVDD3A".

---

## Phase W3 — Digital Domain Provider Names

### Step W3-A: Print Proposed Mapping (Text Output)

Print the proposed digital provider mapping in the conversation before calling UI:

```
Digital domain provider mapping:

  low VDD   {signal}  →  PVDD1DGZ   (VDD pin on all digital pads)
  low VSS   {signal}  →  PVSS1DGZ   (VSS pin on all digital pads)
  high VDD  {signal}  →  PVDD2POC   (VDDPST pin on all digital pads)
  high VSS  {signal}  →  PVSS2DGZ   (VSSPST pin on all digital pads)
```

### Step W3-B: Single Confirm Call (UI)

```
question: "Digital provider mapping — confirm or change?"
options:
  A: "Correct — use {sig1}/{sig2}/{sig3}/{sig4}"  [Recommended]
  B: "Use defaults: VIOL / GIOL / VIOH / GIOH"
  C: "Custom — I'll type 4 names"   [Other free-text]
```

---

## Phase W4 — Signal Directions

### Step W4-A: Auto-Infer Directions (Silent)

Apply direction defaults from Tier 1 rules. Flag only signals with ambiguous names.

| Pattern | Auto direction |
|---------|---------------|
| `RST*`, `SCK*`, `SDI`, `MOSI`, `SLP*`, `SYNC*`, `CS*`, `EN*`, `CLK*` (as input) | input |
| `SDO`, `MISO`, `D[0-9]+`, `DA[0-9]+`, `DOUT*`, `OUT*` | output |
| Unknown patterns | flag as ambiguous |

### Step W4-B: Print Auto-Inferred Directions (Text Output)

Print as markdown before any UI call:

```
Digital IO directions (auto-inferred):

  input:   RSTN  SCK  SDI  SLP  ...
  output:  SDO  D0  D1  D2  D3  D4  D5  D6  D7  D8  ...

  Ambiguous (needs confirmation):  {list only truly ambiguous signals}
```

### Step W4-C: UI Only for Ambiguous Directions

If any ambiguous direction signals: one `AskUserQuestion` call per 4 signals.
If all directions are clear: **skip this UI call entirely**.

---

## Phase W5 — Final Confirmation

### Step W5-A: Print Complete Final Plan (Text Output)

Print the full plan as a markdown table directly in the conversation (NOT in AskUserQuestion preview):

```markdown
## IO Ring Signal Plan — Wizard Confirmed

| # | Signal      | Type                    | Device     |
|---|-------------|-------------------------|------------|
| 0 | RSTN        | Digital IO — input      | PDDW16SDGZ |
...

**Digital Domain:**  IOVDDL (low VDD) / VSS (low VSS) / IOVDDH (high VDD) / IOVSS (high VSS)

**Analog Domains:**
- Domain 1 (DVDD/DVSS): DVSS DVDD VCALB VCALF IBIAS3N ...
- Domain 2 (AVDD/AVSS): AVDD AVSS VINN VINP ...
```

### Step W5-B: Single Confirm Call (UI)

```
question: "Plan ready. Proceed to generate?"
options:
  A: "Generate IO ring now"         [Recommended]
  B: "Fix one signal"               [Other — type correction]
  C: "Restart wizard"
  D: "Cancel"
```

---

## Constraint Output Schema

After all wizard phases, assemble two output objects:

### `geometry` → feeds Step 1 (draft builder)

```json
{
  "placement_order": "clockwise" | "counterclockwise",
  "starting_side":   "top" | "right" | "bottom" | "left",
  "width":           12,
  "height":          12
}
```

`starting_side` tells Step 1 that signal list position 0 maps to `{starting_side}_0`. Step 1 uses this together with `placement_order` to assign all positions.

### `wizard_constraints` → feeds Step 2 (enrichment) as Priority 1

```json
{
  "signal_types": {
    "{signal_name}": "{type}"
    // type values: "analog_io", "analog_power_provider", "analog_ground_provider",
    //              "analog_power_consumer", "analog_ground_consumer",
    //              "digital_io", "digital_power_low", "digital_ground_low",
    //              "digital_power_high", "digital_ground_high"
  },
  "voltage_domains": [
    {
      "vdd_provider":  "{signal_name}",
      "vss_provider":  "{signal_name}",
      "range_from":    "{signal_name}",
      "range_to":      "{signal_name}",
      "device_type":   "PVDD3AC/PVSS3AC" | "PVDD3A/PVSS3A"
    }
  ],
  "digital_providers": {
    "low_vdd":  "{signal_name}",
    "low_vss":  "{signal_name}",
    "high_vdd": "{signal_name}",
    "high_vss": "{signal_name}"
  },
  "directions": {
    "{signal_name}": "input" | "output"
  }
}
```

`device_type` per domain: `"PVDD3AC/PVSS3AC"` (default, uses TACVDD/TACVSS pins) or `"PVDD3A/PVSS3A"` (only when user explicitly selects, uses TAVDD/TAVSS pins).



---

## UI Call Budget (Target)

| Phase | Calls | Notes |
|-------|-------|-------|
| G (Geometry) | 2 | G1: order+side, G2: dimensions |
| W1 (Classification) | ⌈N_ambiguous/4⌉ + 1 confirm | Tier 1 signals auto-classified silently; 1 signal per question |
| W2 (Domains) | 1–2 + 1 device type | Confirm grouping + per-domain PVDD3A? |
| W3 (Digital providers) | 1 | Single confirm/change call |
| W4 (Directions) | ⌈N_ambiguous_dir/4⌉ | Only truly ambiguous directions |
| W5 (Final confirm) | 1 | Text table printed first, then 1 call |

| Signal count | Old design (no Tier split) | New design (Tier 1/2 split) |
|-------------|---------------------------|------------------------------|
| 6 signals   | ~6 calls   | ~4 calls   |
| 20 signals  | ~9 calls   | ~5 calls   |
| 48 signals  | ~18 calls  | ~8 calls   |

The savings come from: auto-classifying Tier 1 signals silently and printing tables as plain text instead of in previews.

---

## AskUserQuestion Usage Rules

1. **Never embed a full signal table in a preview pane** — preview is only visible when an option is focused; use plain text output instead
2. **Never ask about Tier 1 signals** — auto-classify them silently
3. **One question = one decision** — do not conflate classification + domain + direction in one call
4. **Print before ask** — always show the current state as text in the conversation before calling `AskUserQuestion`
5. **2 options for binary decisions** — provider vs consumer, input vs output: use 2 options only (cleaner than 4)
6. **Use "Other" for free-text overrides** — never create a 5th option; use the built-in "Other" for custom names/ranges

---

## Examples

### Example 1 — 6 Signals (All Tier 1)

Input: `VCM, CLKP, VDDIB, VSSIB, DA0, RST`

W1 auto-classifies: VCM → analog_io, CLKP → analog_io, DA0 → digital_io, RST → digital_io
W1 ambiguous: VDDIB, VSSIB (power signals, need provider vs consumer clarification)

Text output shows draft table.
**1 UI call** for VDDIB + VSSIB.
Text output shows updated table.
**1 confirm call**.

Total W1: 2 calls.

---

### Example 2 — 48 Signals

Tier 1 auto (no UI): RSTN, SCK, SDI, SDO, D8–D0, SLP, IOVDDH, IOVSS, IOVDDL,
                      VCM, VINN, VINP, IBIAS3N, IBIAS2N, IBIAS1P, VAMP,
                      IBUF1P–IBUF3N, IBVREF, CLKINN, CLKINP, REFIN, IBIAS_REF,
                      IBIAS, IBIAS2  (≈ 36 signals)

Tier 2 ambiguous (UI): VSS, DVSS, DVDD, VCALB, VCALF, AVDD, AVSS, AVDDBUF,
                        CBVDD, CKVSS, CKVDD, RVSS, RVDD, RVDDH  (≈ 14 signals)

W1: text table → **4 UI calls** (14 ambiguous / 4 per call) → text update → **1 confirm call**
W2: text domain table → **1 UI call** (confirm 4 domains) + **1 device type call** (PVDD3AC vs PVDD3A per domain)
W3: text digital mapping → **1 UI call** (confirm providers)
W4: all directions Tier 1 → **0 UI calls** (all auto)
W5: text final plan → **1 confirm call**

Total: **~8 UI calls** vs ~18 in the original (no Tier 1/2 split) design.
