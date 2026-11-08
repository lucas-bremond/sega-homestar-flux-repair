# ruff: noqa: E501 -- long lines are KiCad S-expression templates, clearer unsplit
"""KiCad schematic for build.py: layout (where parts, wires and power symbols go) and rendering.

The layout is plain data, in absolute sheet millimetres:
    {"parts": {ref: [x, y, mirror]}, "wires": [[[x, y], ...], ...], "power": [[net, x, y, dir], ...]}
It comes from model.yaml's schematic_layout (block-relative, pins by name) or, once the
schematic editor in index.html has exported one, from annotations.json ("schematic").

Drawing rules:
- every known connection is drawn: wires for signal nets, power symbols for power nets;
- a wire's style follows the weakest confidence of the pins it joins (solid when verified,
  dashed for datasheet and assumed), in that level's colour;
- pins with no known net are left open: they are unknown, not unconnected.
"""

import math
import re
import uuid

GRID = 2.54
PIN_LEN = 2.54
STUB = 2.54
NAMESPACE = uuid.UUID("6f1c2a9e-0d5b-4c1e-9a43-7f0e2b8d5c11")
GROUP_ORDER = ["input", "regulator", "mcu", "motor", "shooting_star", "main_led", "unknown", "front_panel"]
ORIGIN = (30.48, 50.8)
DEFAULT_WIDTH = 66.04
VERIFIED_RANK = 3  # photo or better
DIRS = {"L": (-1, 0), "R": (1, 0), "U": (0, -1), "D": (0, 1)}  # sheet coordinates, y down


def uid(*parts: str) -> str:
    return str(uuid.uuid5(NAMESPACE, "/".join(parts)))


def q(text: str) -> str:
    escaped = str(text).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return '"' + escaped + '"'


def natural_key(text: str) -> list:
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", text)]


def hex_rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return tuple(int(color[i : i + 2], 16) for i in (0, 2, 4))


def r2(v: float) -> float:
    return round(v, 2)


# ----------------------------------------------------------------------------- symbols


def symbol_geometry(part: dict) -> dict:
    """Body size and pin ends in symbol coordinates (y up). Pins split left/right in order."""
    pins = list(part["pins"].items())
    half = (len(pins) + 1) // 2
    left, right = pins[:half], pins[half:]
    rows = max(len(left), len(right), 1)
    longest = max(len(name) for _, name in pins)
    # whole multiples of 2 grid steps keep every pin end on the 2.54 mm grid
    steps = 1 if len(pins) <= 2 else max(2, math.ceil((2 + longest * 0.9) / 2))
    body_w = 2 * GRID * steps
    body_h = GRID * (rows + 1)
    top = GRID * math.ceil((rows + 1) / 2)
    placed = []
    for i, (num, name) in enumerate(left):
        placed.append((num, name, -body_w / 2 - PIN_LEN, top - GRID * (i + 1), 0))
    for i, (num, name) in enumerate(right):
        placed.append((num, name, body_w / 2 + PIN_LEN, top - GRID * (i + 1), 180))
    return {"w": body_w, "h": body_h, "top": top, "pins": placed}


def pin_ends(model: dict, parts_layout: dict) -> dict:
    """(ref, pin) -> (x, y, outward direction 'L' or 'R') on the sheet."""
    out = {}
    for ref, (sx, sy, mirror) in parts_layout.items():
        for num, _name, px, py, angle in symbol_geometry(model["parts"][ref])["pins"]:
            if mirror:
                px, angle = -px, 180 - angle
            out[(ref, num)] = (r2(sx + px), r2(sy - py), "L" if angle == 0 else "R")
    return out


def lib_symbol(ref: str, part: dict, geo: dict) -> str:
    font = "(effects (font (size 1.27 1.27)))"
    hidden = "(effects (font (size 1.27 1.27)) hide)"
    show_names = "" if len(part["pins"]) > 2 else "(pin_names hide)"
    w2, top = geo["w"] / 2, geo["top"]
    lines = [
        f"(symbol {q('model:' + ref)} {show_names} (exclude_from_sim no) (in_bom yes) (on_board yes)",
        f'(property "Reference" {q(re.sub(r"[0-9_].*", "", ref) or "X")} (at 0 0 0) {font})',
        f'(property "Value" {q(ref)} (at 0 0 0) {font})',
        f'(property "Footprint" "" (at 0 0 0) {hidden})',
        f'(property "Datasheet" "" (at 0 0 0) {hidden})',
        f"(symbol {q(ref + '_0_1')} (rectangle (start {-w2:.2f} {top:.2f}) (end {w2:.2f} {top - geo['h']:.2f}) "
        f"(stroke (width 0.254) (type default)) (fill (type background))))",
        f"(symbol {q(ref + '_1_1')}",
    ]
    for num, pname, x, y, angle in geo["pins"]:
        lines.append(
            f"(pin passive line (at {x:.2f} {y:.2f} {angle}) (length {PIN_LEN}) "
            f"(name {q(pname)} {font}) (number {q(num)} {font}))"
        )
    lines.append("))")
    return "\n".join(lines)


def power_shape(net: str, direction: str) -> list[list[tuple[float, float]]]:
    """Polylines of a power symbol in sheet-relative coordinates (y down), pin at the origin.
    Ground: three bars; any other rail: a T. Shared with the editor (viewer_template.html)."""
    dx, dy = DIRS[direction]
    px, py = -dy, dx  # perpendicular

    def at(a, b):
        return (r2(dx * a + px * b), r2(dy * a + py * b))

    if net == "GND":
        return [
            [at(0, 0), at(1.27, 0)],
            [at(1.27, -1.27), at(1.27, 1.27)],
            [at(1.9, -0.76), at(1.9, 0.76)],
            [at(2.5, -0.25), at(2.5, 0.25)],
        ]
    return [[at(0, 0), at(1.27, 0)], [at(1.27, -1.27), at(1.27, 1.27)]]


def power_lib_symbol(net: str, direction: str) -> str:
    name = f"model:PWR_{net}_{direction}"
    dx, dy = DIRS[direction]
    tx, ty = 5.08 * dx, -3.81 * dy  # value text beyond the symbol (symbol coordinates: y up)
    polys = " ".join(
        "(polyline (pts "
        + " ".join(f"(xy {x:.2f} {-y:.2f})" for x, y in line)
        + ") (stroke (width 0.254) (type default)) (fill (type none)))"
        for line in power_shape(net, direction)
    )
    return (
        f"(symbol {q(name)} (power) (pin_names (offset 0) hide) (pin_numbers hide) (exclude_from_sim no) (in_bom yes) (on_board yes)"
        f' (property "Reference" "#PWR" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))'
        f' (property "Value" {q(net)} (at {tx:.2f} {ty:.2f} 0) (effects (font (size 1.27 1.27))))'
        f' (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))'
        f' (property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))'
        f" (symbol {q(f'PWR_{net}_{direction}_0_1')} {polys})"
        f" (symbol {q(f'PWR_{net}_{direction}_1_1')} (pin power_in line (at 0 0 0) (length 0) hide"
        f' (name {q(net)} (effects (font (size 1.27 1.27)))) (number "1" (effects (font (size 1.27 1.27)))))))'
    )


# ----------------------------------------------------------------------------- layout


def resolve_layout(model: dict) -> dict:
    """Absolute layout from schematic_layout (block-relative, pins by name) plus auto-stacking."""
    spec_all = model.get("schematic_layout", {})
    by_group: dict[str, list[str]] = {g: [] for g in GROUP_ORDER}
    for ref, part in model["parts"].items():
        by_group[part["group"]].append(ref)
    parts, headers, raw_routes, raw_power = {}, [], [], []
    x0 = ORIGIN[0]
    for group in GROUP_ORDER:
        spec = spec_all.get(group, {})
        oy = ORIGIN[1]
        headers.append([model["blocks"][group]["title"], r2(x0 - 10.16), 40.64])
        bottom = oy
        for ref, pos in spec.get("place", {}).items():
            geo = symbol_geometry(model["parts"][ref])
            parts[ref] = [r2(x0 + pos[0]), r2(oy + pos[1]), len(pos) > 2 and pos[2] == "mirror"]
            bottom = max(bottom, oy + pos[1] - geo["top"] + geo["h"])
        y = GRID * math.ceil((bottom + 12.7) / GRID) if spec.get("place") else oy
        for ref in sorted(set(by_group[group]) - set(spec.get("place", {})), key=natural_key):
            geo = symbol_geometry(model["parts"][ref])
            parts[ref] = [r2(x0 + 10.16), r2(y + geo["top"]), False]
            y += geo["h"] + 12.7
        raw_routes += [(x0, oy, route) for route in spec.get("wires", [])]
        raw_power += [(x0, oy, p) for p in spec.get("power", [])]
        x0 += spec.get("width", DEFAULT_WIDTH)
    ends = pin_ends(model, parts)
    wires = []
    for ox, oy, route in raw_routes:
        points = []
        for step in route:
            if isinstance(step, str):
                ref, num = step.rsplit(".", 1)
                if (ref, num) not in ends:
                    raise ValueError(f"schematic_layout: unknown pin {step}")
                points.append(list(ends[(ref, num)][:2]))
            else:
                points.append([r2(ox + step[0]), r2(oy + step[1])])
        wires.append(points)
    power = [[p[0], r2(ox + p[1]), r2(oy + p[2]), p[3]] for ox, oy, p in raw_power]
    return {"parts": parts, "wires": wires, "power": power, "headers": headers, "right": r2(x0)}


def merge_layout(auto: dict, override: dict | None) -> dict:
    """An exported layout (annotations.json "schematic") replaces the automatic one; parts it
    does not mention keep their automatic place."""
    if not override:
        return auto
    return {
        "parts": {**auto["parts"], **{r: [p[0], p[1], bool(p[2])] for r, p in override.get("parts", {}).items()}},
        "wires": override.get("wires", []),
        "power": override.get("power", []),
        "headers": auto["headers"],
        "right": auto["right"],
    }


def on_segment(p: tuple, a: tuple, b: tuple) -> bool:
    (x, y), (x1, y1), (x2, y2) = p, a, b
    if x1 == x2 == x:
        return min(y1, y2) <= y <= max(y1, y2)
    if y1 == y2 == y:
        return min(x1, x2) <= x <= max(x1, x2)
    return False


def prune_conflicts(model: dict, layout: dict, nets_of: dict) -> tuple[dict, list[str]]:
    """Drop wired groups whose pins no longer agree on one known net (a pin re-assigned in the
    editor, say) so the build falls back to labels for them. Used for the automatic layout only:
    an exported layout is the user's own and its conflicts are errors. viewer_template.html
    applies the same rule."""
    ends = pin_ends(model, layout["parts"])
    pin_at = {tuple(v[:2]): k for k, v in ends.items()}
    parent: dict = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for route in layout["wires"]:
        pts = [tuple(map(r2, p)) for p in route]
        for a, b in zip(pts, pts[1:], strict=False):
            parent[find(a)] = find(b)
    members: dict = {}
    for pt in list(parent):
        if pt in pin_at:
            members.setdefault(find(pt), set()).add(pin_at[pt])
    for net, x, y, _ in layout["power"]:
        members.setdefault(find((r2(x), r2(y))), set()).add(("power", net))
    bad = set()
    for root, items in members.items():
        nets = {nets_of.get(i, (None,))[0] if i[0] != "power" else i[1] for i in items}
        if None in nets or len(nets) > 1:
            bad.add(root)
    if not bad:
        return layout, []
    dropped = sorted({f"{r}.{p}" for root in bad for r, p in members[root] if r != "power"})
    kept = dict(layout)
    kept["wires"] = [w for w in layout["wires"] if find(tuple(map(r2, w[0]))) not in bad]
    kept["power"] = [p for p in layout["power"] if find((r2(p[1]), r2(p[2]))) not in bad]
    return kept, dropped


def analyse(model: dict, layout: dict, nets_of: dict, rank: dict, power_nets: set) -> dict:
    """Check the layout's wires and power symbols against the nets; return what to draw.

    Raises ValueError for anything that would draw a wrong connection."""
    ends = pin_ends(model, layout["parts"])
    pin_at, problems = {}, []
    for k, v in ends.items():
        if tuple(v[:2]) in pin_at:
            other = pin_at[tuple(v[:2])]
            problems.append(f"pins {other[0]}.{other[1]} and {k[0]}.{k[1]} touch; move one of the parts")
        pin_at[tuple(v[:2])] = k
    segments = []
    for i, route in enumerate(layout["wires"]):
        pts = [tuple(map(r2, p)) for p in route]
        if len(pts) < 2:
            problems.append(f"wire {i}: needs two points")
        for a, b in zip(pts, pts[1:], strict=False):
            if a[0] != b[0] and a[1] != b[1]:
                problems.append(f"wire {i}: segment {a}-{b} is not horizontal or vertical")
            if a != b:
                segments.append((a, b, i))
    # connectivity: union-find over wire points (end points join; a pin joins the point it sits on)
    parent: dict = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        parent[find(a)] = find(b)

    for a, b, _ in segments:
        union(a, b)
    endpoint_count: dict = {}
    for a, b, _ in segments:
        for pt in (a, b):
            endpoint_count[pt] = endpoint_count.get(pt, 0) + 1
    for pt in endpoint_count:
        for a, b, i in segments:
            if pt not in (a, b) and on_segment(pt, a, b):
                problems.append(f"wire {i}: another wire ends on its middle at {pt}; split it there")
    for (ref, num), (x, y, _) in ends.items():
        for a, b, i in segments:
            if on_segment((x, y), a, b) and (x, y) not in (a, b):
                problems.append(f"wire {i} runs through pin {ref}.{num}")
    groups: dict = {}
    for pt in endpoint_count:
        groups.setdefault(find(pt), {"points": set(), "pins": set(), "power": []})["points"].add(pt)
    for pt, key in pin_at.items():
        if pt in endpoint_count:
            groups[find(pt)]["pins"].add(key)
    for j, (net, x, y, direction) in enumerate(layout["power"]):
        pt = (r2(x), r2(y))
        if direction not in DIRS:
            problems.append(f"power symbol {j}: direction must be one of {', '.join(DIRS)}")
        if pt in endpoint_count:
            groups[find(pt)]["power"].append(j)
        elif pt in pin_at:
            groups.setdefault(("pin", pt), {"points": {pt}, "pins": {pin_at[pt]}, "power": [j]})
        else:
            problems.append(f"power symbol {net} at {pt} is not on a wire end or pin")
    wired, styled = set(), {}
    for key, g in groups.items():
        nets = {nets_of.get(p, (None, None))[0] for p in g["pins"]} | {layout["power"][j][0] for j in g["power"]}
        if None in nets:
            unknown = [f"{r}.{p}" for r, p in g["pins"] if (r, p) not in nets_of]
            problems.append(f"a wire reaches {', '.join(unknown)}, whose net is unknown")
        nets.discard(None)
        if len(nets) > 1:
            problems.append(
                f"a wire joins nets {', '.join(sorted(nets))} (pins {', '.join(sorted(f'{r}.{p}' for r, p in g['pins']))})"
            )
        if not g["pins"] and not g["power"]:
            problems.append(f"a wire at {sorted(g['points'])[0]} is not connected to any pin")
        if not nets:
            continue
        net = nets.pop()
        confs = [nets_of[p][1] for p in g["pins"]]
        weakest = min(confs, key=rank.__getitem__) if confs else "confirmed"
        styled[key] = (net, weakest)
        wired |= g["pins"]
        if net in power_nets and not g["power"]:
            problems.append(
                f"wired {net} group (pins {', '.join(sorted(f'{r}.{p}' for r, p in g['pins']))}) needs a power symbol"
            )
    if problems:
        raise ValueError("schematic layout problems:\n  " + "\n  ".join(dict.fromkeys(problems)))
    return {
        "segments": segments,
        "find": find,
        "styled": styled,
        "wired": wired,
        "ends": ends,
        "endpoint_count": endpoint_count,
    }


# ----------------------------------------------------------------------------- render


def render(model: dict, layout: dict, nets_of: dict, rank: dict, power_nets: set) -> tuple[str, tuple, dict]:
    """KiCad schematic text, the drawn extent, and a report (unconnected known pins)."""
    colors = {k: hex_rgb(v["color"]) for k, v in model["confidence"].items()}
    a = analyse(model, layout, nets_of, rank, power_nets)
    root = uid("root")
    lib, placed, texts, wires, junctions, labels, powers = [], [], [], [], [], [], []
    for ref, (sx, sy, mirror) in layout["parts"].items():
        part = model["parts"][ref]
        geo = symbol_geometry(part)
        lib.append(lib_symbol(ref, part, geo))
        placed.append(placed_symbol(ref, part, sx, sy, geo, root, mirror))

    def style(conf):
        rgb = colors[conf]
        kind = "solid" if rank[conf] >= VERIFIED_RANK else "dash"
        return f"(stroke (width 0.2) (type {kind}) (color {rgb[0]} {rgb[1]} {rgb[2]} 1))"

    for a_pt, b_pt, _ in a["segments"]:
        net, conf = a["styled"][a["find"](a_pt)]
        wires.append(
            f"(wire (pts (xy {a_pt[0]:.2f} {a_pt[1]:.2f}) (xy {b_pt[0]:.2f} {b_pt[1]:.2f})) {style(conf)} "
            f"(uuid {q(uid('wire', net, str(a_pt), str(b_pt)))}))"
        )
    for pt, n in sorted(a["endpoint_count"].items()):
        pin_here = any(tuple(v[:2]) == pt for v in a["ends"].values())
        if n >= 3 or (n >= 2 and pin_here):
            junctions.append(
                f"(junction (at {pt[0]:.2f} {pt[1]:.2f}) (diameter 0) (color 0 0 0 0) (uuid {q(uid('junction', str(pt)))}))"
            )
    power_entries = list(layout["power"])
    # automatic power symbols: every power-net pin that is not wired gets a stub and a symbol
    unconnected = []
    for (ref, num), (x, y, outward) in sorted(a["ends"].items()):
        net = nets_of.get((ref, num))
        if not net or (ref, num) in a["wired"] or any((r2(p[1]), r2(p[2])) == (x, y) for p in power_entries):
            continue
        if net[0] in power_nets:
            dx = DIRS[outward][0]
            end = (r2(x + dx * STUB), y)
            wires.append(
                f"(wire (pts (xy {x:.2f} {y:.2f}) (xy {end[0]:.2f} {end[1]:.2f})) {style(net[1])} (uuid {q(uid('stub', ref, num))}))"
            )
            power_entries.append([net[0], end[0], end[1], outward])
        else:
            unconnected.append((ref, num))
    used_power = sorted({(p[0], p[3]) for p in power_entries})
    lib += [power_lib_symbol(net, d) for net, d in used_power]
    for j, (net, x, y, d) in enumerate(power_entries):
        ref = f"#PWR{j + 1:03d}"
        dx, dy = DIRS[d]
        powers.append(
            f"(symbol (lib_id {q(f'model:PWR_{net}_{d}')}) (at {x:.2f} {y:.2f} 0) (unit 1) (exclude_from_sim no) "
            f"(in_bom yes) (on_board yes) (dnp no) (uuid {q(uid('pwr', str(j), net))}) "
            f'(property "Reference" {q(ref)} (at {x:.2f} {y:.2f} 0) (effects (font (size 1.27 1.27)) hide)) '
            f'(property "Value" {q(net)} (at {x + 5.08 * dx:.2f} {y + 3.81 * dy:.2f} 0) (effects (font (size 1.27 1.27)))) '
            f'(property "Footprint" "" (at {x:.2f} {y:.2f} 0) (effects (font (size 1.27 1.27)) hide)) '
            f'(property "Datasheet" "" (at {x:.2f} {y:.2f} 0) (effects (font (size 1.27 1.27)) hide)) '
            f'(pin "1" (uuid {q(uid("pwrpin", str(j)))})) '
            f'(instances (project "pcb-model" (path {q("/" + root)} (reference {q(ref)}) (unit 1)))))'
        )
    # one name per wired signal net: on its board pad if it has one, else above its longest horizontal wire
    named = set()
    for key, (net, conf) in sorted(a["styled"].items(), key=lambda kv: str(kv[1])):
        if net in power_nets or net in named:
            continue
        named.add(net)
        rgb = colors[conf]
        pins = [p for p in a["wired"] if nets_of[p][0] == net]
        pads = sorted(p for p in pins if model["parts"][p[0]]["kind"] == "pad")
        if pads:
            x, y, outward = a["ends"][pads[0]]
            ang, just = (180, "right") if outward == "L" else (0, "left")
        else:
            segs = [(p, s) for p, s, _ in a["segments"] if a["find"](p) == key]
            p, s2 = max(segs, key=lambda ps: abs(ps[1][0] - ps[0][0]) + abs(ps[1][1] - ps[0][1]))
            if p[1] == s2[1]:
                x, y, ang, just = r2(round((p[0] + s2[0]) / 2 / 1.27) * 1.27), p[1], 0, "left"
            else:
                x, y, ang, just = p[0], r2(round((p[1] + s2[1]) / 2 / 1.27) * 1.27), 90, "left"
        labels.append(
            f"(label {q(net)} (at {x:.2f} {y:.2f} {ang}) (effects (font (size 1.27 1.27) (color {rgb[0]} {rgb[1]} {rgb[2]} 1)) "
            f"(justify {just} bottom)) (uuid {q(uid('label', 'net', net))}))"
        )
    # fallback: a known signal pin with no wire keeps a label (and is reported)
    for ref, num in unconnected:
        net, conf = nets_of[(ref, num)]
        x, y, outward = a["ends"][(ref, num)]
        rgb = colors[conf]
        ang, just = (180, "right") if outward == "L" else (0, "left")
        labels.append(
            f"(label {q(net)} (at {x:.2f} {y:.2f} {ang}) (effects (font (size 1.27 1.27) (color {rgb[0]} {rgb[1]} {rgb[2]} 1)) "
            f"(justify {just} bottom)) (uuid {q(uid('label', ref, num))}))"
        )
    for title, x, y in layout["headers"]:
        texts.append(
            f"(text {q(title)} (at {x:.2f} {y:.2f} 0) (effects (font (size 2.54 2.54) (bold yes)) (justify left bottom)) "
            f"(uuid {q(uid('hdr', title))}))"
        )
    legend = [
        "Every known connection is drawn. Wire colour = confidence; solid = verified (photo, confirmed, measured), dashed = datasheet or assumed:"
    ] + [f"  {k} — {v['meaning']}" for k, v in sorted(model["confidence"].items(), key=lambda kv: -kv[1]["rank"])]
    legend += ["Open pins are UNKNOWN, not unconnected. Generated from model.yaml and annotations.json."]
    texts.append(
        f"(text {q(chr(10).join(legend))} (at 20.32 15.24 0) (effects (font (size 1.778 1.778)) (justify left top)) (uuid {q(uid('legend'))}))"
    )
    ys = [p[1] for p in layout["parts"].values()]
    drawn = (12.7, 10.16, layout["right"] + 10.16, max(ys) + 15.24)
    board = model["board"]
    text = "\n".join(
        [
            '(kicad_sch (version 20231120) (generator "homestar_build_py") (generator_version "8.0")',
            f"(uuid {q(root)})",
            '(paper "A2")',
            f"(title_block (title {q(board['name'] + ' — partial model')}) (date {q(board['model_date'])}) "
            f'(rev "model") (comment 1 {q(board["marking"])}) '
            f'(comment 2 "Reconstructed from photos; see analysis/pcb-model/model.yaml"))',
            "(lib_symbols",
            *lib,
            ")",
            *texts,
            *wires,
            *junctions,
            *labels,
            *placed,
            *powers,
            '(sheet_instances (path "/" (page "1")))',
            ")",
            "",
        ]
    )
    return text, drawn, {"unconnected": [f"{r}.{p}" for r, p in unconnected], "power_symbols": len(power_entries)}


def placed_symbol(ref: str, part: dict, sx: float, sy: float, geo: dict, root: str, mirror: bool = False) -> str:
    font = "(effects (font (size 1.27 1.27)) (justify left))"
    pins = " ".join(f"(pin {q(num)} (uuid {q(uid('pin', ref, num))}))" for num in part["pins"])
    return (
        f"(symbol (lib_id {q('model:' + ref)}) (at {sx:.2f} {sy:.2f} 0) {'(mirror y) ' if mirror else ''}(unit 1) "
        f"(exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no) (uuid {q(uid('sym', ref))}) "
        f'(property "Reference" {q(ref)} (at {sx - geo["w"] / 2:.2f} {sy - geo["top"] - 1.27:.2f} 0) {font}) '
        f'(property "Value" {q(part["value"])} (at {sx - geo["w"] / 2:.2f} {sy - geo["top"] + geo["h"] + 2.54:.2f} 0) {font}) '
        f'(property "Footprint" "" (at {sx:.2f} {sy:.2f} 0) (effects (font (size 1.27 1.27)) hide)) '
        f'(property "Datasheet" "" (at {sx:.2f} {sy:.2f} 0) (effects (font (size 1.27 1.27)) hide)) '
        f'{pins} (instances (project "pcb-model" (path {q("/" + root)} (reference {q(ref)}) (unit 1)))))'
    )
