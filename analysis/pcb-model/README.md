# Partial electrical model of the main board

**Date:** 2026-11-07
**Board:** `E007-01GE047-02XP REV:00 2018-07-05`
**Status:** partial. 45 of the 133 modelled pins are on a net, and most connections are **hypotheses from photos**. Measure before relying on any of them.

**Open [`index.html`](index.html) in a browser** for the interactive view. It is self-contained and works offline. It has four tabs:

- **Board:** both photos with a clickable box for every part. Select a net or a part to highlight its connections, coloured by confidence, with the evidence for each.
- **Block diagram:** the board's functional blocks and the links between them.
- **Schematic:** the KiCad schematic, exported as SVG.
- **Open questions:** the 8 measurements that would close the most important gaps.

The header checkboxes hide connections by confidence level. For example, untick `assumed` to see only what is backed by a label, a photo or a datasheet.

## Files

| File                                                                                           | What it is                                                                                     |
| ---------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| [`model.yaml`](model.yaml)                                                                     | **Source of truth:** parts, pins, nets, confidence and evidence per connection, open questions |
| [`netlist.md`](netlist.md)                                                                     | Generated tables: nets, evidence, open questions, parts, and a Mermaid block diagram           |
| [`block-diagram.svg`](block-diagram.svg)                                                       | Generated block diagram                                                                        |
| [`pcb-model.kicad_sch`](pcb-model.kicad_sch)                                                   | Generated KiCad schematic: one symbol per part, nets as labels coloured by confidence          |
| [`schematic.svg`](schematic.svg)                                                               | The schematic exported by `kicad-cli` (embedded in `index.html`)                               |
| [`index.html`](index.html)                                                                     | Generated viewer                                                                               |
| [`build.py`](build.py), [`build.sh`](build.sh), [`viewer_template.html`](viewer_template.html) | Generator, full build with KiCad checks, viewer template                                       |

## Confidence levels

Every connection (a pin on a net) has one level. A net is only as certain as its weakest connection.

| Level       | Meaning                                                                                | Connections |
| ----------- | -------------------------------------------------------------------------------------- | ----------- |
| `measured`  | Checked on the board with a meter                                                      | 0           |
| `confirmed` | Silkscreen label, a wire seen soldered to the pad, or a measurement in `REPAIR_LOG.md` | 8           |
| `photo`     | Trace, copper area or tinned strip followed in a close-up                              | 10          |
| `datasheet` | Pin function from the part's datasheet (the part number itself is read from the photo) | 5           |
| `assumed`   | Standard circuit practice or placement only                                            | 22          |

Pins that aren't on any net are **unknown**, not unconnected. The schematic leaves them open, and the viewer draws parts with no known connection as dashed boxes.

## What the tracing found

New facts from the photos, beyond `REPAIR_LOG.md`:

- **Input wiring:** a wire is soldered into one hole of each of `DC+` (red), `DC-` (black) and `R1B` (yellow); the leads are visible from the bottom in `parts/IMG_3631`. The 100 Ω resistor `R1B` (`101`) bridges the `R1B` pad and `DC+`. What the yellow wire carries is unknown (OQ6).
- **U3** reads **`D9924 2006`** in `parts/IMG_3631`, not `9624`. This most likely is a QX9924, a step-down LED driver with a built-in switch; its exposed pad is the switch node. The pin order isn't confirmed, so U3's pins aren't modelled.
- **5 W LED:** the `5WL+` wire lead is bent along a tinned strip that runs to D16's (SK34) cathode (`parts/IMG_3628`).
- **Motor area:**
  - The capacitor between the `M+` and `M-` pads is **C6**. Its label is upside down in `parts/IMG_3619`; C8 is on the bottom, beside U2.
  - R13 (0 Ω) links `M-` to U4 pin 8 (OUTA).
  - A faint trace runs from U4 pin 5 (OUTB) toward `M+`.
  - C9 sits against U4 pin 4 (VDD).
- **U4 orientation:** with its text upright, pin 1 (dimple) is bottom-left, by the `U4` label. Pins 1–4 face the 47 µF capacitor C7.
- **Front panel:** 7 LEDs (D3–D9: 3 red for the timer, 2 yellow, 2 green), 3 push-buttons (SW1–SW3) and the slide switch S1. SW5 is an empty footprint next to Q1.
- **Electrolytic next to `102`:** it is **C11** (100 µF); C10 is the small SMD part below it.

## Open questions

The [open questions](netlist.md#open-questions) list the measurements that would settle the gaps that matter for the fault. The first three:

1. **OQ1:** where U4's motor supply (pin 4) comes from. Its short is what resets the unit.
2. **OQ2:** whether U4's logic supply (pin 1) is on 3.3 V or 5 V. If it's on 3.3 V, a U4 fault pulls the MCU supply down directly.
3. **OQ3:** which U1 pins drive U4's inputs, so you can watch them on a scope.

To record a result, change that connection's confidence in `model.yaml` to `measured` (or add the pin to the right net), then rebuild.

## Build and checks

```sh
./build.sh                  # needs Python with PyYAML and Pillow, and Docker
python -I build.py          # outputs only, without the KiCad steps
```

`build.sh` regenerates the outputs, then uses `kicad-cli` 9.0.9 (Docker image `kicad/kicad:9.0`) to export the schematic's netlist, SVG and electrical rules check (ERC).

Results on 2026-11-07:

- **Netlist round trip:** the netlist KiCad derives from the generated schematic matches `model.yaml` on all 16 nets. This check found and fixed a bug where labels missed off-grid pins.
- **ERC:** 144 findings, all expected:
  - 88 `pin_not_connected`: exactly the 88 unknown pins.
  - 55 `lib_symbol_issues`: the symbols are embedded in the schematic rather than in a KiCad library.
  - 1 `label_dangling`: `5WL-`, a net whose only known member is the pad.
- **Viewer:** a headless Chromium test ([`tests/ui-test.mjs`](tests/ui-test.mjs), run command in its header) passes 14 checks, covering net and part highlighting, the confidence filter, search and all four tabs, with no JavaScript errors.

## Limits

- **Photos only show the surface:** traces under parts and through vias can't be followed, so most links between the two sides are missing.
- **U1 is unmarked:** its pin functions can only be learned by tracing or measuring.
- **Unverified pinouts:** the MX08L pinout comes from `REPAIR_LOG.md`, and the 6206 and SOT-23 pinouts are the common ones for those packages. None of these has been checked against the actual part's datasheet.
- **Approximate positions:** part boxes on the photos come from the YOLO detector (see [`../yolo26/`](../yolo26/README.md)) and from hand placement.
