"""
Quick test script to validate the Tampermonkey image fetch API.

Usage:
  pixi run python test_tm_image_fetch.py [image_url] [output_path]

Requires:
  - Tampermonkey script installed in the shared Chrome profile (chrome_profile)
  - Script exposes window.__GET_IMAGE_BASE64__ on img.alicdn.com pages
"""
import base64
import os
import sys
from pathlib import Path
from typing import Optional

from src.single_product_scraper import setup_driver, _dom_fetch_image_new_tab


def fetch_and_save(driver, image_url: str, output_path: Path) -> bool:
    """Open image in a new tab, pull bytes via Tampermonkey API fallback, and save to disk."""
    driver.get("about:blank")
    driver.execute_script("window.open(arguments[0], '_blank');", image_url)
    new_handle = [h for h in driver.window_handles if h != driver.current_window_handle][0]
    driver.switch_to.window(new_handle)

    data = _dom_fetch_image_new_tab(driver, image_url)
    if not data:
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(data)
    return True


def main():
    image_url = sys.argv[1] if len(sys.argv) > 1 else "https://img.alicdn.com/imgextra/i3/1863639347/O1CN01bbwyok2IuyiHQ7pSZ_!!1863639347.jpg"
    output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("tm_fetch_test.jpg")

    driver = setup_driver()
    try:
        ok = fetch_and_save(driver, image_url, output_path)
        if ok:
            size = output_path.stat().st_size
            print(f"Saved image to {output_path} ({size} bytes)")
        else:
            print("Failed to fetch image via Tampermonkey API and fallbacks.")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
