# Repair log

Investigation log for the Homestar Flux fault described in the [README](README.md).

## Where we are

- [x] **1. Characterize the symptoms**
- [x] **2. Rule out the power adapter**
- [ ] **3. Isolate the faulty area** ← we are here
  - [x] Rule out the motor (disconnect `M+`)
  - [ ] Timer test: button side vs output side
  - [ ] Resistance checks on the `M+`/`M-` pads and the driver's capacitor
  - [ ] Disconnect `M-` and one shooting-star LED wire, press Shooting Star
- [ ] **4. Identify the failed component** (8-pin driver markings, pinout)
- [ ] **5. Source a replacement**
- [ ] **6. Repair**
- [ ] **7. Verify** Move (N and S), Shooting Star and Timer

## Investigation

| #   | Date       | Action                                                | Result                                                                            | Conclusion                                      |
| --- | ---------- | ----------------------------------------------------- | --------------------------------------------------------------------------------- | ----------------------------------------------- |
| 1   | 2026-11-07 | Press Move                                            | Lamp blinks for a split second, N/S LED flashes then goes out, motor doesn't turn | The unit resets                                 |
| 2   | 2026-11-07 | Press Shooting Star                                   | Same; SS LED flashes then goes out                                                | Same fault                                      |
| 3   | 2026-11-07 | Try 5 V/2 A and 5 V/4 A adapters                      | No change                                                                         | Not the adapter                                 |
| 4   | 2026-11-07 | Open the unit, check the motor and belt               | Belt intact, motor shaft never moves                                              | Not the transmission                            |
| 5   | 2026-11-07 | Review the manual                                     | Shooting stars only run while rotating; rotation reverses (N/S); 5 W at 5 V       | Brownout reset suspected; normal draw about 1 A |
| 6   | 2026-11-07 | Press Shooting Star alone, rotation never switched on | Same reset                                                                        | Not specific to the Move button                 |
| 7   | 2026-11-07 | Photograph both sides of the board                    | No visible damage; pads and main parts identified                                 | See [board reference](#board-reference)         |
| 8   | 2026-11-07 | Inspect the shooting-star mechanism                   | It depends on the motor turning                                                   | Both buttons go through the motor path          |
| 9   | 2026-11-07 | Disconnect `M+`, press Shooting Star                  | Still resets                                                                      | Motor ruled out; the fault is upstream of it    |

## Findings

- **Failure mode: brownout reset.** Move and Shooting Star both make the microcontroller switch on the motor output. Something then pulls the supply down far enough to reset the microcontroller, which reboots into its power-on state because the slide power switch stays ON: lamp on, every function off.
- **Not the adapter.** Normal draw is about 1 A (5 W at 5 V), and a 4 A adapter changes nothing: the overload is inside the unit.
- **Shooting Star uses the motor.** Shooting stars only run while rotating, and the mechanism depends on the motor turning.
- **Not the motor.** With `M+` disconnected, Shooting Star still resets the unit.
- **No visible damage** on either side of the board.

## Suspects

| Rank | Suspect                                                                                                                          | Status                   |
| ---- | -------------------------------------------------------------------------------------------------------------------------------- | ------------------------ |
| 1    | Motor driver chip (8-pin next to `M+`) failed short, or a shorted part on its supply, such as the electrolytic beside it         | Open                     |
| 2    | Remaining wiring: `M-` (still connected) or the shooting-star LED wires shorted in the harness, or the shooting-star LED circuit | Open                     |
| 3    | The button press itself (board flex or button circuit)                                                                           | Open, Timer test decides |
|      | Power adapter                                                                                                                    | Ruled out (#3)           |
|      | Motor                                                                                                                            | Ruled out (#9)           |

## Next tests

1. **Timer test.** Press Timer, then Move once, with the motor still disconnected. Timer works normally → the fault is on the output side. Timer also resets → the button press is the trigger: tap the case, wiggle the cable, and trigger Shooting Star by bridging its pads with tweezers.
2. **Resistance checks.** With the power off (unplugged, power switch ON), measure from the free `M+` pad and from `M-` to `DC-` and to `DC+`, then across the electrolytic next to the 8-pin chip. Near 0 Ω → shorted driver output or supply. A diode-like reading in one direction only is normal (internal diodes).
3. **Disconnect the outputs.** Disconnect `M-` and one shooting-star LED wire too, then press Shooting Star. Still resets → the board, with the driver chip as prime suspect. Stops → the wiring or the shooting-star LED: reconnect one wire at a time.
4. **Identify the driver.** Photograph the 8-pin chip's markings to get its part number, pinout and a replacement.
5. **If still unresolved.** Test D12, D13 and D15 in diode mode (about 0 V both ways = shorted), check the capacitors around U2 for cracks, and measure U2's pins to ground. Feed any dead-short node from a current-limited supply (under 1 V, about 1 A) and find the part that warms up.
6. **Optional.** Watch the supply with a scope, or the input current with a USB power meter, while pressing Shooting Star.

Avoid pressing Move or Shooting Star repeatedly until the fault is isolated: each press pushes a short through whatever has failed.

## Board reference

Main board marking: `E007-01GE047-02XP`, `REV:00`, `2018-07-05`.

| Button side                                                    | Labelled side                                                      |
| -------------------------------------------------------------- | ------------------------------------------------------------------ |
| ![Board, button side](photos/2026-11-07-board-button-side.jpg) | ![Board, labelled side](photos/2026-11-07-board-labelled-side.jpg) |

- **Button side:** buttons, LEDs, inductors, the 16-pin and 8-pin chips.
- **Labelled side:** silkscreen labels for the pads and buttons, U2, U3 and most small parts.

| Pads            | Connection                           |
| --------------- | ------------------------------------ |
| `DC+` / `DC-`   | 5 V input from the USB cable         |
| `5WL+` / `5WL-` | Main 5 W LED                         |
| `SSL+` / `SSL-` | Shooting-star LED                    |
| `M+` / `M-`     | Rotation motor (brushed DC, 2 wires) |
| `R1B`           | Unknown, next to `DC+`               |

- **Power switch:** hard ON/OFF slide switch.
- **Main LED driver:** 8-pin chip U3 (labelled side), with an SK34 Schottky diode (D16) and two `R390` (0.39 Ω) current-sense resistors. Works.
- **Microcontroller:** most likely the 16-pin chip in the middle of the button side.
- **Motor driver:** most likely the 8-pin chip next to `M+` (button side), with an electrolytic capacitor beside it.
- **Near the motor and shooting-star pads (labelled side):** U2 (3 legs plus a tab, capacitors on both sides, looks like a small regulator), a small transistor next to R16, glass diodes D12, D13 and D15, capacitors C1, C5, C8 and C13.
- **Front panel:** Timer (15/30/60 min LEDs), Move (N/S LEDs), Shooting Star (SS LED), ON LED.

## Open questions

- Part number of the 8-pin chip next to `M+` (needs a sharp close-up of its markings).
- What `R1B` connects to.
- Optional close-ups: the 16-pin chip, U2, the transistor by R16, D12/D13/D15.
