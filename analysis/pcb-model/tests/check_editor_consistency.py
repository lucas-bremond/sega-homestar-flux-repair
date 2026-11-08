"""Check that build.py merges editor exports exactly as the page does, and accepts them.

Run after tests/ui-test.mjs, which writes, for each scenario, the page's export
(shots/edit-*.json) and the nets the page computed from it (shots/edit-*nets.json):
    python -I tests/check_editor_consistency.py
"""

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUILD = HERE.parent / "build.py"
SCENARIOS = [("edit-annotations.json", "edit-nets.json"), ("edit-schematic.json", "edit-schematic-nets.json")]

sys.path.insert(0, str(HERE.parent))
import build  # noqa: E402
from schematic import render  # noqa: E402

failed = False
for exported, page_nets in SCENARIOS:
    out = subprocess.run(
        [sys.executable, "-I", str(BUILD), "--annotations", str(HERE / "shots" / exported), "--dump-nets"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    built = {k: sorted(map(tuple, v)) for k, v in json.loads(out).items()}
    page = {k: sorted(map(tuple, v)) for k, v in json.loads((HERE / "shots" / page_nets).read_text()).items()}
    if built != page:
        failed = True
        print(f"{exported}: page and build disagree:", sorted(set(built.items()) ^ set(page.items())))
        continue
    # the build must also accept the exported schematic layout
    base = build.load_model(BUILD.parent / "model.yaml")
    ann = build.load_annotations(HERE / "shots" / exported)
    model = build.apply_annotations(base, ann)
    rank = {k: v["rank"] for k, v in model["confidence"].items()}
    _, layout, _ = build.build_layout(model, ann)
    try:
        render(model, layout, build.pin_nets(model), rank, set(model.get("power_nets", [])))
    except ValueError as err:
        failed = True
        print(f"{exported}: the build refuses the layout: {err}")
        continue
    print(f"{exported}: page and build agree on {len(built)} nets; layout accepted")
sys.exit(1 if failed else 0)
