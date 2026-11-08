"""Check that build.py merges an editor export exactly as the page does.

Run after tests/ui-test.mjs, which writes shots/edit-annotations.json (the page's export)
and shots/edit-nets.json (the nets the page computed from it):
    python -I tests/check_editor_consistency.py
"""

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
out = subprocess.run(
    [
        sys.executable,
        "-I",
        str(HERE.parent / "build.py"),
        "--annotations",
        str(HERE / "shots/edit-annotations.json"),
        "--dump-nets",
    ],
    capture_output=True,
    text=True,
    check=True,
).stdout
build = {k: sorted(map(tuple, v)) for k, v in json.loads(out).items()}
page = {k: sorted(map(tuple, v)) for k, v in json.loads((HERE / "shots/edit-nets.json").read_text()).items()}
if build != page:
    print("page and build disagree:", sorted(set(build.items()) ^ set(page.items())))
    sys.exit(1)
print(f"page and build agree on {len(build)} nets")
