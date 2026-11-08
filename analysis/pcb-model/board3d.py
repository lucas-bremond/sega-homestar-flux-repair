"""Board geometry and the 3D viewer (board-3d.html) for build.py.

Everything is in the top-view board frame, in millimetres: origin at the outline's top-left,
x to the right, y down. bottom-1.jpg maps to it by a scale and a top-to-bottom mirror (the
board was flipped about its long axis between the photos); top-1.jpg, taken at an angle, by
a homography fitted on points visible in both photos.
"""

import base64
import io
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

TEXTURE_PX_PER_MM = 12
TALL_KINDS = {"led", "switch", "electrolytic"}
LED_COLOURS = {"red": "#ef4444", "yellow": "#facc15", "green": "#4ade80"}
WIRE_COLOURS = {
    "red": "#dc2626",
    "black": "#18181b",
    "yellow": "#facc15",
    "orange": "#f97316",
    "brown": "#78350f",
}


class Geometry:
    def __init__(self, model: dict, repo: Path):
        g = model["geometry"]
        self.repo = repo
        self.x0, self.y1 = g["bottom_x0"], g["bottom_y1"]
        outline_px = np.asarray(g["outline_bottom_px"], float)
        if g.get("board_width_mm"):
            self.scale = (outline_px[:, 0].max() - outline_px[:, 0].min()) / g["board_width_mm"]
            self.scale_source = f"board width measured as {g['board_width_mm']} mm"
        else:
            self.scale = g["bottom_px_per_mm"]
            self.scale_source = "package dimensions of U2 and U3 (about ±5 %)"
        self.thickness = g["thickness_mm"]
        self.outline = [self.from_bottom(x, y) for x, y in outline_px]
        xs, ys = zip(*self.outline, strict=True)
        self.width, self.height = max(xs), max(ys)
        pairs = g["top_points"]
        self.h_top = fit_homography([p[0] for p in pairs.values()], [self.from_bottom(*p[1]) for p in pairs.values()])
        self.residuals = {
            name: float(np.hypot(*np.subtract(self.from_top(*p[0]), self.from_bottom(*p[1]))))
            for name, p in pairs.items()
        }

    def from_bottom(self, x: float, y: float) -> tuple[float, float]:
        return ((x - self.x0) / self.scale, (self.y1 - y) / self.scale)

    def from_top(self, x: float, y: float) -> tuple[float, float]:
        p = self.h_top @ [x, y, 1.0]
        return (p[0] / p[2], p[1] / p[2])

    def texture(self, side: str, photo: str, enhanced: bool = False) -> str:
        """The photo warped into the board frame, as a JPEG data URI; `enhanced` boosts local
        contrast so copper under the solder mask shows (the same pixels, nothing added)."""
        r = TEXTURE_PX_PER_MM
        size = (math.ceil(self.width * r), math.ceil(self.height * r))
        if side == "top":
            to_board = np.diag([r, r, 1.0]) @ self.h_top
        else:  # bottom: board = ((x - x0) / s, (y1 - y) / s)
            s = self.scale
            to_board = np.diag([r, r, 1.0]) @ np.array([[1 / s, 0, -self.x0 / s], [0, -1 / s, self.y1 / s], [0, 0, 1]])
        inv = np.linalg.inv(to_board)
        inv /= inv[2, 2]
        img = ImageOps.exif_transpose(Image.open(self.repo / photo)).convert("RGB")
        warped = img.transform(size, Image.PERSPECTIVE, tuple(inv.flatten()[:8]), Image.BICUBIC)
        if enhanced:
            warped = ImageOps.autocontrast(warped, cutoff=1)
            warped = warped.filter(ImageFilter.UnsharpMask(radius=10, percent=260, threshold=0))
            warped = ImageEnhance.Color(warped).enhance(1.5)
        buf = io.BytesIO()
        warped.save(buf, format="JPEG", quality=80)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()

    def trace(self, side: str, points: list) -> list:
        to_board = self.from_top if side == "top" else self.from_bottom
        return [[round(c, 2) for c in to_board(x, y)] for x, y in points]

    def footprint(self, ref: str, part: dict, override: dict) -> dict | None:
        """Board-frame placement of a part's 3D body, or None if it has no box."""
        box = part.get("box", {})
        side = "top" if "top" in box else "bottom" if "bottom" in box else None
        if side is None:
            return None
        x0, y0, x1, y1 = box[side]
        to_board = self.from_top if side == "top" else self.from_bottom
        corners = [to_board(x, y) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
        bx0, bx1 = min(c[0] for c in corners), max(c[0] for c in corners)
        by0, by1 = min(c[1] for c in corners), max(c[1] for c in corners)
        w, length = bx1 - bx0, by1 - by0
        cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
        if side == "top" and part["kind"] in TALL_KINDS:
            # photographed at an angle: tall parts lean up the image, so their base is the box's bottom
            foot = min(w, override.get("d", w))
            cy = by1 - foot / 2
            length = foot
        if "at" in override:
            cx, cy = override["at"]
        return {"side": side, "x": round(cx, 2), "y": round(cy, 2), "w": round(w, 2), "l": round(length, 2)}


def fit_homography(src: list, dst: list) -> np.ndarray:
    """Least-squares DLT homography mapping src points to dst points."""
    rows = []
    for (x, y), (u, v) in zip(src, dst, strict=True):
        rows.append([x, y, 1, 0, 0, 0, -u * x, -u * y, -u])
        rows.append([0, 0, 0, x, y, 1, -v * x, -v * y, -v])
    _, _, vt = np.linalg.svd(np.asarray(rows, float))
    h = vt[-1].reshape(3, 3)
    return h / h[2, 2]


def body(ref: str, part: dict, fp: dict, override: dict) -> dict:
    """3D body description for the viewer: shape, size (mm) and colour."""
    kind, value = part["kind"], str(part["value"]).lower()
    w, length = fp["w"], fp["l"]
    b = {"shape": "box", "w": w * 0.85, "l": length * 0.85, "h": 1.0, "color": "#3f3f46"}
    if kind == "ic":
        b.update(h=2.4 if "18" in str(part.get("package", "")) else 1.6, color="#27272a")
    elif kind == "transistor":
        b.update(w=min(w, 3.0), l=min(length, 3.0), h=1.1, color="#27272a")
    elif kind == "resistor":
        b.update(w=min(w, 6.5), l=min(length, 6.5), h=0.6, color="#1c1917")
    elif kind == "capacitor":
        b.update(w=min(w, 4.5), l=min(length, 4.5), h=0.8, color="#a8a29e")
    elif kind == "diode" and "glass" in value:
        b.update(shape="rod", d=1.6, len=max(w, length) * 0.8, axis="x" if w >= length else "y", color="#c2410c")
    elif kind == "diode":
        b.update(w=min(w, 5.0), l=min(length, 5.0), h=2.2, color="#18181b")
    elif kind == "electrolytic":
        b.update(shape="cylinder", d=override.get("d", min(w, length)), h=override.get("h", 11), color="#1e293b")
    elif kind == "inductor":
        b.update(w=w * 0.9, l=length * 0.9, h=override.get("h", 6), color="#3f3f46")
    elif kind == "led":
        colour = next((c for name, c in LED_COLOURS.items() if name in value), "#e5e7eb")
        b.update(shape="led", d=5.0, h=18.0, spacer=10.0, color=colour)
    elif kind == "switch" and "slide" in value:
        b.update(w=12.0, l=6.5, h=6.5, color="#9ca3af")
    elif kind == "switch":
        b.update(shape="button", w=6.0, l=6.0, h=3.5, stem=13.0, color="#18181b")
    elif kind == "pad":
        b.update(shape="pad", d=3.0, h=0.2, color="#d4d4d8", wire=WIRE_COLOURS.get(part.get("wire", ""), "#71717a"))
    b.update({k: v for k, v in override.items() if k in ("h", "d")})
    return {k: (round(v, 2) if isinstance(v, float) else v) for k, v in b.items()}


def write_board_3d(model: dict, data: dict, here: Path, repo: Path, path: Path) -> dict:
    """Write board-3d.html; return the fit residuals (mm) for the build log."""
    geo = Geometry(model, repo)
    overrides = model["geometry"].get("bodies", {})
    parts3d = {}
    for ref, part in model["parts"].items():
        override = overrides.get(ref, {})
        fp = geo.footprint(ref, part, override)
        if fp:
            parts3d[ref] = {**fp, "body": body(ref, part, fp, override)}
    payload = {
        **data,
        "board": {
            **model["board"],
            "outline": [[round(x, 2), round(y, 2)] for x, y in geo.outline],
            "width": round(geo.width, 2),
            "height": round(geo.height, 2),
            "thickness": geo.thickness,
            "scale_source": geo.scale_source,
            "max_residual_mm": round(max(geo.residuals.values()), 2),
        },
        "parts3d": parts3d,
        "traces": [
            {"net": t["net"], "side": t["side"], "evidence": t["evidence"], "points": geo.trace(t["side"], t["points"])}
            for t in model.get("traces", [])
        ],
        "textures": {
            f"{side}{suffix}": geo.texture(side, model["photos"][side]["file"], enhanced=bool(suffix))
            for side in ("top", "bottom")
            for suffix in ("", "_enhanced")
        },
    }
    vendor = here / "vendor" / "three-0.170.0"
    page = (here / "viewer3d_template.html").read_text(encoding="utf-8")
    page = page.replace("__TITLE__", model["board"]["name"])
    page = page.replace("__THREE_URI__", js_data_uri(vendor / "three.module.min.js"))
    page = page.replace("__ORBIT_URI__", js_data_uri(vendor / "OrbitControls.js"))
    page = page.replace("__DATA__", json.dumps(payload, ensure_ascii=False).replace("</", "<\\/"))
    path.write_text(page, encoding="utf-8")
    return geo.residuals


def js_data_uri(path: Path) -> str:
    return "data:text/javascript;base64," + base64.b64encode(path.read_bytes()).decode()
