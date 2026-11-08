#!/bin/sh
# Regenerate every output from model.yaml and check the KiCad schematic.
# Needs Python 3.10+ with PyYAML and Pillow, and Docker (for kicad-cli 9).
set -eu
cd "$(dirname "$0")"
PYTHON=${PYTHON:-python3}

"$PYTHON" -I build.py
docker run --rm -u "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD":/w -w /w kicad/kicad:9.0 sh -c '
  kicad-cli sch export netlist --format kicadsexpr -o kicad-netlist.net pcb-model.kicad_sch >/dev/null
  kicad-cli sch export svg --exclude-drawing-sheet -o /tmp/svg pcb-model.kicad_sch >/dev/null
  sed "s| date [0-9/: ]*</title>|</title>|" /tmp/svg/pcb-model.svg > schematic.svg  # drop the export timestamp
  kicad-cli sch erc --severity-all -o erc.rpt pcb-model.kicad_sch >/dev/null'
"$PYTHON" -I build.py --check-netlist kicad-netlist.net
echo "ERC findings by type:"
grep -oE '^\[[a-z_]+\]' erc.rpt | sort | uniq -c | sort -rn
"$PYTHON" -I build.py  # embed the fresh schematic.svg in index.html
