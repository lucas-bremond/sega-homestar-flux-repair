"""Generate the board model outputs from model.yaml.

Outputs, all written next to this script:
    netlist.md           nets, parts, unknown pins and open questions as tables
    block-diagram.svg    block diagram with confidence-coloured links
    pcb-model.kicad_sch  KiCad schematic (one symbol per part, nets as labels)
    index.html           self-contained viewer (photos, nets, diagram, schematic)
    board-3d.html        self-contained 3D view (three.js 0.170, vendored), via board3d.py

The schematic SVG embedded in index.html (schematic.svg) and the KiCad netlist
used by --check-netlist are exported by kicad-cli; see README.md.

Usage:
    python -I build.py                       # validate and generate
    python -I build.py --check-netlist F.net # compare a kicad-cli netlist with the model
"""

import argparse
import base64
import copy
import html
import io
import json
import re
import sys
import uuid
from pathlib import Path

import yaml
from PIL import Image, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parent))
from board3d import write_board_3d  # noqa: E402
from schematic import merge_layout, prune_conflicts, render, resolve_layout, symbol_geometry  # noqa: E402

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
PHOTO_WIDTH_PX = 2400  # sharp enough to place trace points when zoomed
NAMESPACE = uuid.UUID("6f1c2a9e-0d5b-4c1e-9a43-7f0e2b8d5c11")

# ----------------------------------------------------------------------------- model


def load_model(path: Path) -> dict:
    model = yaml.safe_load(path.read_text(encoding="utf-8"))
    for part in model["parts"].values():
        part["pins"] = {str(k): str(v) for k, v in part["pins"].items()}
    for net in model["nets"].values():
        net["nodes"] = [{"ref": n[0], "pin": str(n[1]), "conf": n[2], "evidence": n[3]} for n in net["nodes"]]
    return model


def load_annotations(path: Path) -> dict:
    """The editor's file (index.html exports it): traces, part-box and connection overrides."""
    ann = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return {
        "version": ann.get("version", 1),
        "traces": ann.get("traces", []),
        "boxes": ann.get("boxes", {}),
        "connections": ann.get("connections", []),
        "schematic": ann.get("schematic"),
    }


def validate_annotations(base: dict, ann: dict) -> list[str]:
    errors = []
    parts, sides, levels = base["parts"], base["photos"], base["confidence"]
    for t in ann["traces"]:
        tid = t.get("id", "?")
        if t.get("side") not in sides:
            errors.append(f"trace {tid}: unknown side {t.get('side')!r}")
        if len(t.get("points", [])) < 2:
            errors.append(f"trace {tid}: needs at least 2 points")
        if not t.get("net"):
            errors.append(f"trace {tid}: no net")
    for ref, by_side in ann["boxes"].items():
        if ref not in parts:
            errors.append(f"box override: unknown part {ref}")
            continue
        for side, box in by_side.items():
            if side not in sides:
                errors.append(f"box override {ref}: unknown side {side!r}")
            elif box is not None and not (len(box) == 4 and box[0] < box[2] and box[1] < box[3]):
                errors.append(f"box override {ref}.{side}: expected [x0, y0, x1, y1] with x0 < x1, y0 < y1")
    for ref in (ann.get("schematic") or {}).get("parts", {}):
        if ref not in parts:
            errors.append(f"schematic layout: unknown part {ref}")
    for c in ann["connections"]:
        ref, pin = c.get("ref"), str(c.get("pin"))
        if ref not in parts or pin not in parts[ref]["pins"]:
            errors.append(f"connection override: unknown pin {ref}.{pin}")
        if c.get("net") and c.get("conf") not in levels:
            errors.append(f"connection override {ref}.{pin}: unknown confidence {c.get('conf')!r}")
    return errors


def apply_annotations(base: dict, ann: dict) -> dict:
    """The model with the editor's annotations applied. viewer_template.html applies the same rules."""
    model = copy.deepcopy(base)
    model["traces"] = [dict(t) for t in ann["traces"]]
    for ref, by_side in ann["boxes"].items():
        box = model["parts"][ref].setdefault("box", {})
        for side, value in by_side.items():
            if value is None:
                box.pop(side, None)
            else:
                box[side] = list(value)
    for c in ann["connections"]:
        ref, pin = c["ref"], str(c["pin"])
        for net in model["nets"].values():
            net["nodes"] = [n for n in net["nodes"] if (n["ref"], n["pin"]) != (ref, pin)]
        if c.get("net"):
            net = model["nets"].setdefault(c["net"], {"description": "Added in the editor.", "nodes": []})
            net["nodes"].append({"ref": ref, "pin": pin, "conf": c["conf"], "evidence": c.get("evidence", "")})
    model["nets"] = {name: net for name, net in model["nets"].items() if net["nodes"]}
    for t in model["traces"]:
        if t["net"] not in model["nets"]:
            model.setdefault("_errors", []).append(f"trace {t.get('id', '?')}: net {t['net']!r} does not exist")
    return model


def validate(model: dict) -> list[str]:
    """Return a list of problems; empty when the model is consistent."""
    errors = []
    levels = model["confidence"]
    parts = model["parts"]
    seen: dict[tuple[str, str], str] = {}
    for name, net in model["nets"].items():
        for node in net["nodes"]:
            key = (node["ref"], node["pin"])
            if node["ref"] not in parts:
                errors.append(f"net {name}: unknown part {node['ref']}")
            elif node["pin"] not in parts[node["ref"]]["pins"]:
                errors.append(f"net {name}: {node['ref']} has no pin {node['pin']}")
            if node["conf"] not in levels:
                errors.append(f"net {name}: unknown confidence {node['conf']!r}")
            if key in seen:
                errors.append(f"{key[0]}.{key[1]} is on both {seen[key]} and {name}")
            seen[key] = name
    for ref, part in parts.items():
        if part["group"] not in model["blocks"]:
            errors.append(f"{ref}: group {part['group']!r} is not a block")
        for side in part.get("box", {}):
            if side not in model["photos"]:
                errors.append(f"{ref}: box on unknown photo {side!r}")
    for q in model["open_questions"]:
        for ref, pin in q["pins"]:
            if ref not in parts or str(pin) not in parts[ref]["pins"]:
                errors.append(f"{q['id']}: unknown pin {ref}.{pin}")
    for a, b, conf, _ in model["links"]:
        for block in (a, b):
            if block not in model["blocks"]:
                errors.append(f"link {a}-{b}: unknown block {block}")
        if conf not in levels:
            errors.append(f"link {a}-{b}: unknown confidence {conf!r}")
    return errors


def pin_nets(model: dict) -> dict[tuple[str, str], tuple[str, str]]:
    """Map (ref, pin) to (net name, confidence)."""
    return {(n["ref"], n["pin"]): (name, n["conf"]) for name, net in model["nets"].items() for n in net["nodes"]}


def net_confidence(model: dict, net: dict) -> str:
    """A net is only as certain as its weakest connection."""
    rank = {k: v["rank"] for k, v in model["confidence"].items()}
    return min((n["conf"] for n in net["nodes"]), key=rank.__getitem__)


# ----------------------------------------------------------------------------- netlist.md


def md_escape(text: str) -> str:
    return str(text).replace("|", "\\|")


def write_netlist_md(model: dict, path: Path) -> None:
    nets_of = pin_nets(model)
    lines = [
        "# Board model: netlist",
        "",
        f"Generated by `build.py` from `model.yaml` ({model['board']['marking']}). Do not edit by hand.",
        "",
        "## Confidence levels",
        "",
        "| Level | Meaning |",
        "| ----- | ------- |",
    ]
    for level, info in sorted(model["confidence"].items(), key=lambda kv: -kv[1]["rank"]):
        lines.append(f"| `{level}` | {md_escape(info['meaning'])} |")
    lines += ["", "## Nets", ""]
    lines += ["| Net | Weakest link | Connections | Description |", "| --- | --- | --- | --- |"]
    for name, net in model["nets"].items():
        nodes = ", ".join(f"{n['ref']}.{n['pin']} ({n['conf']})" for n in net["nodes"])
        lines.append(
            f"| `{md_escape(name)}` | `{net_confidence(model, net)}` | {md_escape(nodes)} | "
            f"{md_escape(net['description'])} |"
        )
    lines += ["", "### Evidence per connection", ""]
    lines += ["| Net | Pin | Confidence | Evidence |", "| --- | --- | --- | --- |"]
    for name, net in model["nets"].items():
        for n in net["nodes"]:
            pin_name = model["parts"][n["ref"]]["pins"][n["pin"]]
            lines.append(
                f"| `{md_escape(name)}` | {n['ref']}.{n['pin']} ({md_escape(pin_name)}) | "
                f"`{n['conf']}` | {md_escape(n['evidence'])} |"
            )
    lines += ["", "## Open questions", ""]
    lines += ["| ID | Question | Pins | Check |", "| --- | --- | --- | --- |"]
    for q in model["open_questions"]:
        pins = ", ".join(f"{r}.{p}" for r, p in q["pins"])
        lines.append(f"| {q['id']} | {md_escape(q['title'])} | {pins} | {md_escape(q['check'])} |")
    lines += ["", "## Parts", ""]
    lines += ["| Ref | Value | Block | Pins on a net | Unknown pins |", "| --- | --- | --- | --- | --- |"]
    for ref, part in sorted(model["parts"].items(), key=lambda kv: natural_key(kv[0])):
        known = [p for p in part["pins"] if (ref, p) in nets_of]
        unknown = [p for p in part["pins"] if (ref, p) not in nets_of]
        lines.append(
            f"| {ref} | {md_escape(part['value'])} | {model['blocks'][part['group']]['title']} | "
            f"{len(known)} of {len(part['pins'])} | {', '.join(unknown) or '—'} |"
        )
    lines += ["", "## Block diagram", "", "```mermaid", "flowchart LR"]
    for key, block in model["blocks"].items():
        lines.append(f'    {key}["{block["title"]}<br/><small>{block["subtitle"]}</small>"]')
    for a, b, conf, label in model["links"]:
        arrow = "-->" if conf in ("measured", "confirmed", "photo", "datasheet") else "-.->"
        lines.append(f'    {a} {arrow}|"{label} ({conf})"| {b}')
    lines += ["```", ""]
    path.write_text("\n".join(align_tables(lines)), encoding="utf-8")


def align_tables(lines: list[str]) -> list[str]:
    """Pad Markdown table columns the way Prettier does, so the file passes a Prettier check."""
    out, block = [], []
    for line in lines + [""]:
        if line.startswith("|"):
            block.append(line)
            continue
        if block:
            rows = [[c.strip() for c in re.split(r"(?<!\\)\|", r)[1:-1]] for r in block]
            widths = [max(3, *(len(r[i]) for r in rows if i < len(r))) for i in range(len(rows[0]))]
            for k, row in enumerate(rows):
                cells = ["-" * w if k == 1 else c.ljust(w) for c, w in zip(row, widths, strict=True)]
                out.append("| " + " | ".join(cells) + " |")
            block = []
        out.append(line)
    return out[:-1]


def natural_key(text: str) -> list:
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", text)]


# ----------------------------------------------------------------------------- block diagram


def block_diagram_svg(model: dict) -> str:
    colors = {k: v["color"] for k, v in model["confidence"].items()}
    bw, bh, gx, gy, margin = 230, 74, 90, 70, 30
    blocks = model["blocks"]
    cols = max(b["col"] for b in blocks.values()) + 1
    rows = max(b["row"] for b in blocks.values()) + 1
    width = margin * 2 + cols * bw + (cols - 1) * gx
    height = margin * 2 + rows * bh + (rows - 1) * gy + 40

    def box(key: str) -> tuple[float, float]:
        b = blocks[key]
        return margin + b["col"] * (bw + gx), margin + b["row"] * (bh + gy)

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'font-family="system-ui, sans-serif" role="img" aria-label="Board block diagram">',
        "<defs>",
    ]
    for level, color in colors.items():
        out.append(
            f'<marker id="arrow-{level}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
            f'markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{color}"/></marker>'
        )
    out.append("</defs>")
    for a, b, conf, label in model["links"]:
        ax, ay = box(a)
        bx, by = box(b)
        x1, y1, x2, y2 = edge_points(ax, ay, bx, by, bw, bh)
        dash = "" if conf in ("measured", "confirmed", "photo") else ' stroke-dasharray="6 4"'
        out.append(
            f'<g class="link" data-from="{a}" data-to="{b}"><line x1="{x1:.0f}" y1="{y1:.0f}" '
            f'x2="{x2:.0f}" y2="{y2:.0f}" stroke="{colors[conf]}" stroke-width="2.2"{dash} '
            f'marker-end="url(#arrow-{conf})"/>'
            f'<text x="{(x1 + x2) / 2:.0f}" y="{(y1 + y2) / 2 - 6:.0f}" font-size="12" '
            f'text-anchor="middle" fill="{colors[conf]}" paint-order="stroke" stroke="#fff" '
            f'stroke-width="4">{html.escape(label)}</text></g>'
        )
    for key, block in blocks.items():
        x, y = box(key)
        fill = "#fef2f2" if key == "motor" else "#f8fafc"
        stroke = "#dc2626" if key == "motor" else "#475569"
        out.append(
            f'<g class="block" data-block="{key}"><rect x="{x}" y="{y}" width="{bw}" height="{bh}" '
            f'rx="8" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>'
            f'<text x="{x + bw / 2}" y="{y + 30}" font-size="15" font-weight="600" '
            f'text-anchor="middle" fill="#0f172a">{html.escape(block["title"])}</text>'
            f'<text x="{x + bw / 2}" y="{y + 52}" font-size="11.5" text-anchor="middle" '
            f'fill="#475569">{html.escape(block["subtitle"])}</text></g>'
        )
    lx, ly = margin, height - 22
    for level, info in sorted(model["confidence"].items(), key=lambda kv: -kv[1]["rank"]):
        out.append(
            f'<line x1="{lx}" y1="{ly}" x2="{lx + 26}" y2="{ly}" stroke="{info["color"]}" '
            f'stroke-width="2.5"/><text x="{lx + 32}" y="{ly + 4}" font-size="12" '
            f'fill="#334155">{level}</text>'
        )
        lx += 130
    out.append(
        f'<text x="{width - margin}" y="{ly + 4}" font-size="12" text-anchor="end" '
        f'fill="#dc2626">red block: fault area</text>'
    )
    out.append("</svg>")
    return "\n".join(out)


def edge_points(ax, ay, bx, by, bw, bh) -> tuple[float, float, float, float]:
    """Connect two boxes from the nearest edges' midpoints."""
    acx, acy, bcx, bcy = ax + bw / 2, ay + bh / 2, bx + bw / 2, by + bh / 2
    if abs(bcx - acx) * bh >= abs(bcy - acy) * bw:
        sign = 1 if bcx > acx else -1
        return acx + sign * bw / 2, acy, bcx - sign * bw / 2, bcy
    sign = 1 if bcy > acy else -1
    return acx, acy + sign * bh / 2, bcx, bcy - sign * bh / 2


# ----------------------------------------------------------------------------- KiCad schematic


def kicad_nets(netlist_text: str) -> dict[str, set[tuple[str, str]]]:
    """Parse the nets of a kicad-cli 'kicadsexpr' netlist (labelled nets only)."""
    nets = {}
    for block in re.findall(
        r"\(net \(code \"?\d+\"?\) \(name \"([^\"]*)\"\)(.*?)\)\s*(?=\(net |\)\s*\)\s*$)", netlist_text, flags=re.S
    ):
        name, body = block
        nodes = {n for n in re.findall(r'\(node \(ref "([^"]+)"\) \(pin "([^"]+)"\)', body) if not n[0].startswith("#")}
        nets[name.lstrip("/")] = nodes
    return nets


def check_netlist(model: dict, netlist_path: Path) -> list[str]:
    exported = kicad_nets(netlist_path.read_text(encoding="utf-8"))
    problems = []
    for name, net in model["nets"].items():
        want = {(n["ref"], n["pin"]) for n in net["nodes"]}
        got = exported.get(name)
        if got is None:
            problems.append(f"net {name} missing from the KiCad netlist")
        elif got != want:
            problems.append(f"net {name}: model {sorted(want)} != KiCad {sorted(got)}")
    labelled = {k for k in exported if not k.startswith(("Net-(", "unconnected-("))}
    for extra in sorted(labelled - set(model["nets"])):
        problems.append(f"KiCad has a net {extra} that the model does not")
    return problems


# ----------------------------------------------------------------------------- HTML viewer


def photo_data_uri(rel_path: str) -> tuple[str, float]:
    img = ImageOps.exif_transpose(Image.open(REPO / rel_path)).convert("RGB")
    scale = PHOTO_WIDTH_PX / img.width
    img = img.resize((PHOTO_WIDTH_PX, round(img.height * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=78)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode(), scale


def write_html(
    model: dict, diagram_svg: str, drawn: tuple, path: Path, base: dict, annotations: dict, schematic_data: dict
) -> None:
    """index.html gets the base model and the annotations separately: its editor applies and edits them."""
    photos = {}
    for side, info in model["photos"].items():
        uri, scale = photo_data_uri(info["file"])
        photos[side] = {
            "uri": uri,
            "w": round(info["size"][0] * scale),
            "h": round(info["size"][1] * scale),
            "scale": scale,
            "file": info["file"],
        }
    schematic_svg = HERE / "schematic.svg"
    data = {
        "board": model["board"],
        "confidence": model["confidence"],
        "parts": base["parts"],
        "nets": base["nets"],
        "annotations": annotations,
        "schematic": schematic_data,
        "questions": model["open_questions"],
        "blocks": model["blocks"],
        "photos": {k: {kk: vv for kk, vv in v.items() if kk != "uri"} for k, v in photos.items()},
    }
    page = HTML_TEMPLATE
    page = page.replace("__TITLE__", html.escape(model["board"]["name"]))
    page = page.replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    page = page.replace("__TOP_URI__", photos["top"]["uri"])
    page = page.replace("__BOTTOM_URI__", photos["bottom"]["uri"])
    page = page.replace("__DIAGRAM__", diagram_svg)
    if schematic_svg.exists():
        svg = schematic_svg.read_text(encoding="utf-8")
        svg = re.sub(r"<\?xml[^>]*>\s*", "", svg)
        svg = re.sub(r"<!DOCTYPE[^>]*>\s*", "", svg)
        x0, y0, x1, y1 = drawn
        svg = re.sub(
            r'width="[^"]*mm" height="[^"]*mm" viewBox="[^"]*"',
            f'viewBox="{x0:.2f} {y0:.2f} {x1 - x0:.2f} {y1 - y0:.2f}"',
            svg,
            count=1,
        )
        page = page.replace("__SCHEMATIC__", svg)
    else:
        page = page.replace(
            "__SCHEMATIC__",
            "<p>schematic.svg not found: export it with kicad-cli (see README.md) and re-run build.py.</p>",
        )
    path.write_text(page, encoding="utf-8")


HTML_TEMPLATE = (
    (HERE / "viewer_template.html").read_text(encoding="utf-8") if (HERE / "viewer_template.html").exists() else ""
)


# ----------------------------------------------------------------------------- main


def build_layout(model: dict, annotations: dict) -> tuple[dict, dict, list[str]]:
    """The automatic layout (model.yaml, minus wired groups whose pins no longer share a net)
    and the layout to draw (the exported one if annotations.json has it)."""
    auto_layout, dropped = prune_conflicts(model, resolve_layout(model), pin_nets(model))
    exported = annotations.get("schematic")
    return auto_layout, merge_layout(auto_layout, exported), [] if exported else dropped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", type=Path, default=HERE / "model.yaml")
    parser.add_argument("--annotations", type=Path, default=HERE / "annotations.json")
    parser.add_argument("--check-netlist", type=Path, help="kicad-cli netlist to compare")
    parser.add_argument("--dump-nets", action="store_true", help="print the merged nets as JSON and stop")
    args = parser.parse_args()

    base = load_model(args.model)
    annotations = load_annotations(args.annotations)
    errors = validate_annotations(base, annotations)
    model = apply_annotations(base, annotations) if not errors else base
    errors += model.pop("_errors", []) + validate(model)
    if errors:
        print("model errors:\n  " + "\n  ".join(errors))
        return 1
    if args.check_netlist:
        problems = check_netlist(model, args.check_netlist)
        print("\n".join(problems) or f"KiCad netlist matches the model ({len(model['nets'])} nets)")
        return 1 if problems else 0
    if args.dump_nets:
        print(
            json.dumps(
                {n: sorted([x["ref"], x["pin"], x["conf"]] for x in net["nodes"]) for n, net in model["nets"].items()}
            )
        )
        return 0

    write_netlist_md(model, HERE / "netlist.md")
    diagram = block_diagram_svg(model)
    (HERE / "block-diagram.svg").write_text(diagram + "\n", encoding="utf-8")
    rank = {k: v["rank"] for k, v in model["confidence"].items()}
    power_nets = set(model.get("power_nets", []))
    auto_layout, layout, dropped = build_layout(model, annotations)
    if dropped:
        print(f"warning: hand-laid wires dropped, their pins no longer share one net: {', '.join(dropped)}")
    try:
        sch_text, drawn, report = render(model, layout, pin_nets(model), rank, power_nets)
    except ValueError as err:
        print(err)
        return 1
    (HERE / "pcb-model.kicad_sch").write_text(sch_text, encoding="utf-8")
    if report["unconnected"]:
        print(f"warning: known pins left as labels (no wire in the layout): {', '.join(report['unconnected'])}")
    if not HTML_TEMPLATE:
        print("viewer_template.html missing")
        return 1
    schematic_data = {
        "auto": auto_layout,
        "geometry": {ref: symbol_geometry(part) for ref, part in model["parts"].items()},
        "powerNets": sorted(power_nets),
    }
    write_html(model, diagram, drawn, HERE / "index.html", base, annotations, schematic_data)
    data3d = {
        "confidence": model["confidence"],
        "parts": model["parts"],
        "nets": model["nets"],
        "netConfidence": {n: net_confidence(model, net) for n, net in model["nets"].items()},
        "questions": model["open_questions"],
        "blocks": model["blocks"],
    }
    residuals = write_board_3d(model, data3d, HERE, REPO, HERE / "board-3d.html")
    worst = max(residuals, key=residuals.get)
    print(f"3D: top photo fit on {len(residuals)} points, worst {worst} {residuals[worst]:.2f} mm")
    n_pins = sum(len(p["pins"]) for p in model["parts"].values())
    n_known = len(pin_nets(model))
    print(
        f"{len(model['parts'])} parts, {len(model['nets'])} nets, {n_known} of {n_pins} pins on a net, "
        f"{len(model['open_questions'])} open questions"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
