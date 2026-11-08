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

| File                                                                                                                     | What it is                                                                                                                          |
| ------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------- |
| [`model.yaml`](model.yaml)                                                                                               | **Source of truth:** parts, pins, nets, confidence and evidence per connection, open questions                                      |
| [`annotations.json`](annotations.json)                                                                                   | Edits from the viewer's editor, applied on top of `model.yaml`: traces, part-box and connection overrides (see [Editing](#editing)) |
| [`netlist.md`](netlist.md)                                                                                               | Generated tables: nets, evidence, open questions, parts, and a Mermaid block diagram                                                |
| [`block-diagram.svg`](block-diagram.svg)                                                                                 | Generated block diagram                                                                                                             |
| [`pcb-model.kicad_sch`](pcb-model.kicad_sch)                                                                             | Generated KiCad schematic: wires for verified connections, coloured labels for the rest                                             |
| [`schematic.svg`](schematic.svg)                                                                                         | The schematic exported by `kicad-cli` (embedded in `index.html`)                                                                    |
| [`index.html`](index.html)                                                                                               | Generated viewer                                                                                                                    |
| [`board-3d.html`](board-3d.html)                                                                                         | Generated 3D view (see [3D view](#3d-view))                                                                                         |
| [`build.py`](build.py), [`build.sh`](build.sh), [`viewer_template.html`](viewer_template.html)                           | Generator, full build with KiCad checks, viewer template                                                                            |
| [`board3d.py`](board3d.py), [`viewer3d_template.html`](viewer3d_template.html), [`vendor/`](vendor/three-0.170.0/README) | 3D geometry and page, and the vendored three.js 0.170.0 (MIT)                                                                       |

## 3D view

**Open [`board-3d.html`](board-3d.html)** in a browser (self-contained, works offline, needs WebGL).

- **What it shows:** the board with both photos mapped onto its faces, and every modelled part as a simple 3D body on its side of the board. Wires leave their pads in their real colours.
- **Controls:** drag to orbit, scroll to zoom, right-drag to pan. **Top**, **Bottom** and **3D** set the view; **X-ray board** makes the board see-through, which is useful for nets that cross sides.
- **Traced copper** (on by default): the copper actually followed in the close-ups, drawn as copper strips on the right side of the board. This is the evidence for the wired connections. Hover over a strip to see its source photo; selecting a net lights its strips.
- **Enhanced photo:** swaps in contrast-boosted textures (the same photos, no pixels added) in which the copper under the solder mask shows as outlines across the whole board. Use it to follow traces by eye; nothing in it has been traced.
- **Selection:**
  - Click a part, or pick a net, part or open question in the side panel.
  - A net draws lines joining its parts (the shortest tree through them), each coloured by the weaker end's confidence. These lines show the model's connections, **not the copper route**.
  - An open question highlights the parts to probe.

How it is built (`board3d.py`, from the `geometry` section of `model.yaml`):

- **Frame:** `bottom-1.jpg` is close to straight-on, so it defines the board frame: one scale, plus a top-to-bottom mirror, because the board was flipped about its long axis between the photos.
- **Outline:** segmented from the green board in `bottom-1.jpg`.
- **Top photo:** `top-1.jpg` is taken at an angle. It maps to the frame by a homography fitted on 13 points visible on both photos (wire-lead holes and mounting holes). 12 of them fit within 0.6 mm; the worst, `DC-`, is off by 1.2 mm. The build prints these residuals.
- **Scale:** 17.9 px/mm on `bottom-1.jpg`, from U3's and U2's package dimensions. That makes the board **96 × 47 mm, about ±5 %**. To use a measurement instead, set `geometry.board_width_mm` to the measured width of the outline (left to right) and rebuild.
- **Bodies:** sized from each part's kind, package and photo box. Heights are typical values for the package, not measurements. Tall parts are placed at the base of their photo box, because they lean in the angled photo.

Accuracy: positions are within about 1–2 mm, and heights are estimates. Treat it as a map for finding parts and probe points, not as a mechanical model.

## Confidence levels

Every connection (a pin on a net) has one level. A net is only as certain as its weakest connection.

| Level       | Meaning                                                                                | Connections |
| ----------- | -------------------------------------------------------------------------------------- | ----------- |
| `measured`  | Checked on the board with a meter                                                      | 0           |
| `confirmed` | Silkscreen label, a wire seen soldered to the pad, or a measurement in `REPAIR_LOG.md` | 8           |
| `photo`     | Trace, copper area or tinned strip followed in a close-up                              | 8           |
| `datasheet` | Pin function from the part's datasheet (the part number itself is read from the photo) | 5           |
| `assumed`   | Standard circuit practice or placement only                                            | 24          |

Pins that aren't on any net are **unknown**, not unconnected. The schematic leaves them open, and the viewer draws parts with no known connection as dashed boxes.

## What the tracing found

New facts from the photos, beyond `REPAIR_LOG.md`:

- **Input wiring:** a wire is soldered into one hole of each of `DC+` (red), `DC-` (black) and `R1B` (yellow); the leads are visible from the bottom in `parts/IMG_3631`. The 100 Ω resistor `R1B` (`101`) bridges the `R1B` pad and `DC+`. What the yellow wire carries is unknown (OQ6).
- **U3** reads **`D9924 2006`** in `parts/IMG_3631`, not `9624`. This most likely is a QX9924, a step-down LED driver with a built-in switch; its exposed pad is the switch node. The pin order isn't confirmed, so U3's pins aren't modelled.
- **5 W LED:** the `5WL+` wire lead is bent along a tinned strip that runs to D16's (SK34) cathode (`parts/IMG_3628`).
- **Motor area:**
  - The capacitor across the motor pads is **C6** (its label is upside down in `parts/IMG_3619`; C8 is on the bottom, beside U2). Traces in a contrast-enhanced close-up run from each end of C6 to the `M+` and `M-` pads.
  - A trace runs from U4 pin 5 (OUTB) to `M+`, and one from pin 8 (OUTA) to R13 (0 Ω). That R13's other end goes to `M-` is still only placement.
  - C9 sits against U4 pin 4 (VDD); no trace followed.
- **U4 orientation:** with its text upright, pin 1 (dimple) is bottom-left, by the `U4` label. Pins 1–4 face the 47 µF capacitor C7.
- **Front panel:** 7 LEDs (D3–D9: 3 red for the timer, 2 yellow, 2 green), 3 push-buttons (SW1–SW3) and the slide switch S1. SW5 is an empty footprint next to Q1.
- **Electrolytic next to `102`:** it is **C11** (100 µF); C10 is the small SMD part below it.

**Audit (2026-11-08).** Four connections were labelled `photo` on placement alone: C1 to U2 pin 3, C9 to U4 pin 4, R13 to `M-` and R3 to `SSL-`. They are now `assumed`, and only connections backed by a followed trace, copper area or soldered wire count as verified.

## Editing

`index.html` has an editor for the annotations. Click **✎ Edit annotations** on the Board tab:

- **Draw trace:** click points along copper you can follow in a photo, then double-click, press Enter or click **Finish trace**. The trace takes the selected net; change it and add its evidence in the side panel.
- **Select / move:**
  - **Traces:** select one to drag its points. Drag a small square to insert a point; Alt-click or right-click a point to delete it. **Extend** adds points at the end, and Delete removes the trace.
  - **Parts:** select one to drag its box or resize it by the corners, add or remove its box on either photo, and edit each pin's net, confidence and evidence. For example, record a meter check by setting the pin's confidence to `measured`. "(unknown)" takes the pin off its net, and "New net…" creates a net.
- **Undo** (Ctrl+Z) steps back one edit.
- **Saving:** edits are kept in the browser (localStorage) and restored on reload.

Edits stay in the browser until you build them. **Export annotations.json**, save it over `analysis/pcb-model/annotations.json`, and run `./build.sh`. That regenerates the netlist, the schematic and both viewers. The build checks the file first: unknown parts or pins, traces on nets that don't exist, malformed boxes and invalid confidence levels are refused.

A connection promoted to `photo` or better without a wire in `schematic_layout` gets a build warning and a label in the schematic. Add it to `schematic_layout` to draw it as a wire. **Import…** loads an `annotations.json` back into the editor.

`model.yaml` is never edited by the page, so its comments and hand-written structure stay intact. The editor and `build.py` apply annotations by the same rules: the 2D test exports a set of edits, and `tests/check_editor_consistency.py` checks that the build derives the same nets from it as the page.

## Schematic

`pcb-model.kicad_sch` draws a **wire** only for a verified connection (`photo`, `confirmed` or `measured`). Everything else keeps a net label coloured by its confidence. Pins with neither a wire nor a label are unknown. The wired clusters are laid out by hand in `schematic_layout` in `model.yaml`:

| Block          | Wired                                                   |
| -------------- | ------------------------------------------------------- |
| Input          | `DC+` pad ↔ R1B ↔ `R1B` pad                             |
| Motor driver   | U4 pin 5 ↔ C6 ↔ `M+` pad; C6 ↔ `M-` pad; U4 pin 8 ↔ R13 |
| 5 W LED driver | `5WL+` pad ↔ D16                                        |

`build.py` refuses a wire that:

- joins two nets;
- touches a pin it shouldn't;
- runs diagonally;
- lands in the middle of another wire;
- ends on a connection below `photo`.

It also refuses a model where a verified connection has no wire. Promote a connection to `measured` in `model.yaml`, then add its wire to `schematic_layout`.

## Open questions

The [open questions](netlist.md#open-questions) list the measurements that would settle the gaps that matter for the fault. The first three:

1. **OQ1:** where U4's motor supply (pin 4) comes from. Its short is what resets the unit.
2. **OQ2:** whether U4's logic supply (pin 1) is on 3.3 V or 5 V. If it's on 3.3 V, a U4 fault pulls the MCU supply down directly.
3. **OQ3:** which U1 pins drive U4's inputs, so you can watch them on a scope.

To record a result, change that connection's confidence in `model.yaml` to `measured` (or add the pin to the right net), then rebuild.

## Build and checks

```sh
./build.sh                  # needs Python with PyYAML, Pillow and NumPy, and Docker
python -I build.py          # outputs only, without the KiCad steps
```

`build.sh` regenerates the outputs, then uses `kicad-cli` 9.0.9 (Docker image `kicad/kicad:9.0`) to export the schematic's netlist, SVG and electrical rules check (ERC).

Results on 2026-11-07:

- **Netlist round trip:** the netlist KiCad derives from the generated schematic matches `model.yaml` on all 16 nets. This check found and fixed a bug where labels missed off-grid pins.
- **ERC:** 144 findings, all expected:
  - 88 `pin_not_connected`: exactly the 88 unknown pins.
  - 55 `lib_symbol_issues`: the symbols are embedded in the schematic rather than in a KiCad library.
  - 1 `label_dangling`: `5WL-`, a net whose only known member is the pad.
- **3D view:** a headless Chromium test with software WebGL ([`tests/ui3d-test.mjs`](tests/ui3d-test.mjs)) passes 10 checks: the scene renders, the views switch, clicking U4 in the scene selects it, net and question selection light the right parts, `M+` lights only its traced copper, and the trace and enhanced-photo toggles work. No JavaScript errors.
- **Editor:** the 2D test also drives the editor through 12 more checks: draw a trace, name it, drag a point, move a box, change a connection, undo, export, restore after reload, discard and import. `tests/check_editor_consistency.py` then confirms the build merges the exported file into the same 16 nets as the page.
- **2D viewer:** a headless Chromium test ([`tests/ui-test.mjs`](tests/ui-test.mjs), run command in its header) passes 14 checks, covering net and part highlighting, the confidence filter, search and all four tabs, with no JavaScript errors.

## Limits

- **Photos only show the surface:** traces under parts and through vias can't be followed, so most links between the two sides are missing.
- **U1 is unmarked:** its pin functions can only be learned by tracing or measuring.
- **Unverified pinouts:** the MX08L pinout comes from `REPAIR_LOG.md`, and the 6206 and SOT-23 pinouts are the common ones for those packages. None of these has been checked against the actual part's datasheet.
- **Approximate positions:** part boxes on the photos come from the YOLO detector (see [`../yolo26/`](../yolo26/README.md)) and from hand placement.
