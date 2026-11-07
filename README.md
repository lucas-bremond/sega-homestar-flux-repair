# Sega Homestar Flux repair

Repairing a Sega Toys Homestar Flux home planetarium whose rotation and shooting-star functions stopped working.

**Status:** under investigation. See [REPAIR_LOG.md](REPAIR_LOG.md) for progress, findings and next steps.

## The device

The Homestar Flux (Sega Toys, 2018) is an optical home planetarium developed with planetarium creator Takayuki Ohira. A 5 W LED projects a star disc onto the ceiling, powered by a 5 V/2 A USB adapter. Its functions:

- **Move:** rotates the sky (diurnal motion), anticlockwise (N) or clockwise (S)
- **Shooting Star:** a shooting star about every 30 seconds while the sky rotates
- **Timer:** auto-off after 15, 30 or 60 minutes (otherwise after about 3 hours)

## The problem

- The main lamp turns on and projects the star map normally.
- Pressing **Move** or **Shooting Star** makes the lamp blink for a split second. The function's LED flashes, then goes out, and nothing else happens.
- The rotation motor never turns, and the belt is intact.
- Changing the power adapter (5 V/2 A or 5 V/4 A) makes no difference.

## Repository layout

| Path                  | Contents                                                                                             |
| --------------------- | ---------------------------------------------------------------------------------------------------- |
| `README.md`           | This overview                                                                                        |
| `REPAIR_LOG.md`       | Investigation log, findings and next steps                                                           |
| `docs/manual.pdf`     | Official manual (English and German), SporsPartners GmbH & Co. KG, 2018                              |
| `docs/B07JB9Q3FW.pdf` | Third-party instruction page from Manuals+; unofficial, some specs conflict with the official manual |
| `photos/`             | Board photos (`top-*`, `bottom-*`) and part close-ups (`parts/`)                                     |
| `analysis/retrace/`   | Evaluation of re:trace, an automated PCB photo analysis tool, on these photos (not usable here)      |

## Safety

Everything inside runs off the external 5 V adapter, so there is no mains voltage in the unit. Mind the bright 5 W LED when the case is open.
