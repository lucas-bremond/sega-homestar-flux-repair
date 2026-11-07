"""Show what re:trace classes as copper in a board photo.

re:trace finds traces by colour: every pixel inside its copper HSV/LAB ranges
is kept, then skeletonized into "traces". This script prints the share of the
photo inside that mask and writes a side-by-side image (photo | mask in
magenta) so the mask can be checked by eye.

Usage (from a venv with re:trace installed):
    python -I copper_mask.py PHOTO OUTPUT.jpg
"""

import argparse
from pathlib import Path

import cv2
import numpy as np
from retrace.detection import trace_extractor

MAGENTA_BGR = np.array([255, 0, 255])
OUTPUT_WIDTH_PX = 1600


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("photo", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    image = cv2.imread(str(args.photo))
    if image is None:
        raise SystemExit(f"cannot read {args.photo}")

    # Same private helper re:trace's pipeline calls before skeletonizing.
    mask = trace_extractor._copper_mask(image) > 0
    print(f"{args.photo.name}: {mask.mean():.1%} of pixels classed as copper")

    overlay = image.copy()
    overlay[mask] = (0.4 * overlay[mask] + 0.6 * MAGENTA_BGR).astype(np.uint8)
    side_by_side = np.hstack([image, overlay])
    scale = OUTPUT_WIDTH_PX / side_by_side.shape[1]
    small = cv2.resize(side_by_side, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    cv2.imwrite(str(args.output), small, [cv2.IMWRITE_JPEG_QUALITY, 80])


if __name__ == "__main__":
    main()
