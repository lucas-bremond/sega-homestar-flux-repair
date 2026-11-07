"""Test re:trace's OCR and part matcher with hand-placed chip boxes.

re:trace's detector finds no components on these photos, so its OCR never
runs. This script bypasses detection: it hands re:trace's own OCR and matcher
a box around each known chip, then runs raw EasyOCR on the same crop with and
without a rotation search, and finally looks up the true markings in
re:trace's part database.

Usage (from a venv with re:trace[ocr] installed, run from the repo root):
    python -I analysis/retrace/scripts/ocr_check.py photos CROPS_DIR
"""

import argparse
from pathlib import Path

import cv2
import easyocr
from retrace.core.pipeline import Component
from retrace.detection.ocr import read_markings
from retrace.identification.matcher import identify_components, lookup_part

# (photo, reference, marking read by eye, box x, y, w, h in full-size pixels)
CHIPS = [
    ("parts/IMG_3619.jpg", "U4", "MX08L 1949H", 1510, 1440, 640, 580),
    ("parts/IMG_3629.jpg", "U2", "6206A 1952/33", 1280, 1580, 770, 730),
    ("parts/IMG_3628.jpg", "U3", "9624 (blurred)", 330, 420, 740, 800),
]
LOOKUPS = ["MX08L", "MX08", "6206A", "XC6206", "9624", "SS8050", "SK34"]
ROTATIONS_DEG = [90, 180, 270]


def format_results(results: list) -> list[tuple[str, float]]:
    return [(text, round(float(confidence), 2)) for _, text, confidence in results]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("photos", type=Path, help="the repo's photos/ directory")
    parser.add_argument("crops", type=Path, help="where to write the chip crops")
    args = parser.parse_args()
    args.crops.mkdir(parents=True, exist_ok=True)

    reader = easyocr.Reader(["en"], gpu=False, verbose=False)
    for photo, ref, truth, x, y, w, h in CHIPS:
        image = cv2.imread(str(args.photos / photo))
        crop_path = args.crops / f"ocr-{ref}.jpg"
        cv2.imwrite(str(crop_path), image[y : y + h, x : x + w])

        chip = Component(id=ref, label="ic", confidence=1.0, bbox=(x, y, w, h))
        read_markings(image, [chip])
        identify_components([chip])
        plain = format_results(reader.readtext(str(crop_path), detail=1))
        rotated = format_results(
            reader.readtext(str(crop_path), detail=1, rotation_info=ROTATIONS_DEG)
        )
        print(f"{ref} (by eye: {truth})")
        print(f"  re:trace OCR: {chip.marking!r} -> match: {chip.part_number or 'none'}")
        print(f"  raw EasyOCR: {plain}")
        print(f"  raw EasyOCR + rotation search: {rotated}")

    for marking in LOOKUPS:
        hit = lookup_part(marking)
        print(f"lookup {marking!r}: {hit['part'] if hit else 'no match'}")


if __name__ == "__main__":
    main()
