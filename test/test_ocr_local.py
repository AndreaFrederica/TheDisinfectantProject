"""
Quick utility to run OCR on local image files (including webp -> png conversion).

Usage:
    pixi run python -m test.test_ocr_local path/to/img1 [path/to/img2 ...]
If no args are provided, it will look into scraped_data/**/images/detail and main for samples.
"""
import glob
import os
import sys
from pathlib import Path

# Ensure repo root is on sys.path when executed directly
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.single_product_scraper import _run_ocr_from_file


def iter_default_paths():
    patterns = [
        "scraped_data/**/images/detail/*.*",
        "scraped_data/**/images/main/*.*",
    ]
    for pat in patterns:
        for path in glob.glob(pat, recursive=True):
            yield path


def main():
    targets = sys.argv[1:] or list(iter_default_paths())
    if not targets:
        print("No image files found. Pass file paths as arguments.")
        return

    cache = {}
    for path in targets:
        if not os.path.isfile(path):
            continue
        print(f"\n=== OCR {path} ===")
        res = _run_ocr_from_file(path, cache=cache)
        if not res:
            print("  OCR failed or empty result.")
            continue
        text = (res.get("full_text") or "").strip()
        print(f"  Text length: {len(text)}")
        sample = text[:200].replace("\n", "\\n")
        print(f"  Sample: {sample}")


if __name__ == "__main__":
    main()
