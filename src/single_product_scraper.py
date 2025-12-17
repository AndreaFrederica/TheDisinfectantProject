
import base64
import io
import hashlib
import json
import re
import time
import os
import sys
import tempfile
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict, field
from urllib.parse import urlparse

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.driver_cache import DriverCacheManager
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException


@dataclass
class OCRTextLine:
    """Single OCR line with text, score and bounding box."""
    text: str
    score: Optional[float]
    box: List[List[float]]


@dataclass
class OCRResult:
    """OCR result for a single image."""
    image_url: str
    full_text: str
    lines: List[OCRTextLine] = field(default_factory=list)


@dataclass
class SizeInfo:
    """Size information with availability"""
    name: str
    available: bool


@dataclass
class StyleInfo:
    """Style variation information"""
    style_name: str
    image_url: str
    available: bool
    sizes: List[SizeInfo]
    ocr: Optional[OCRResult] = None


@dataclass
class ShopInfo:
    """Shop information"""
    name: str
    url: str
    rating: str
    good_review_rate: Optional[str] = None


@dataclass
class ShippingInfo:
    """Shipping information"""
    delivery: Optional[str] = None
    freight: Optional[str] = None
    delivery_address: Optional[str] = None
    guarantees: Optional[List[str]] = None


@dataclass
class PriceInfo:
    """Price information"""
    coupon_price: Optional[str] = None
    original_price: Optional[str] = None
    sales: Optional[str] = None


@dataclass
class CouponInfo:
    """Coupon information"""
    title: Optional[str] = None
    text: Optional[str] = None


@dataclass
class ReviewInfo:
    """Review information"""
    user: str
    meta: str
    content: str
    images: List[str]


@dataclass
class ProductDetails:
    """Product detailed information"""
    reviews: List[ReviewInfo]
    parameters: Dict[str, str]
    parameters_raw: str
    image_details: List[str]
    image_details_raw: str
    image_details_ocr: List[OCRResult] = field(default_factory=list)
    main_images_ocr_text: str = ""
    detail_images_ocr_text: str = ""


@dataclass
class ProductInfo:
    """Basic product information"""
    title: str
    url: str
    shop: ShopInfo
    shipping: ShippingInfo
    price: PriceInfo
    coupons: List[CouponInfo]


@dataclass
class ProductData:
    """Complete product data structure"""
    product_info: ProductInfo
    styles: List[StyleInfo]
    product_details: ProductDetails


def setup_driver():
    """Initializes and returns a Chrome WebDriver instance."""
    options = webdriver.ChromeOptions()
    profile_path = os.path.abspath('chrome_profile')
    if not os.path.exists(profile_path):
        os.makedirs(profile_path)
    options.add_argument(f'user-data-dir={profile_path}')
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument('--ignore-certificate-errors')
    driver_cache_dir = os.path.abspath(os.path.join(profile_path, "driver_cache"))
    os.makedirs(driver_cache_dir, exist_ok=True)
    cache_manager = DriverCacheManager(root_dir=driver_cache_dir, valid_range=30)
    service = Service(ChromeDriverManager(cache_manager=cache_manager).install())
    driver = webdriver.Chrome(service=service, options=options)
    return driver


# OCR helpers
_ocr_client = None


def _get_ocr_client():
    """Lazily create and cache a PaddleOCR client."""
    global _ocr_client
    if _ocr_client is not None:
        return _ocr_client

    try:
        from paddleocr import PaddleOCR
    except Exception as exc:  # ImportError or runtime errors
        print(f"OCR library not available: {exc}")
        return None

    try:
        _ocr_client = PaddleOCR(
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False
        )
    except Exception as exc:
        print(f"Failed to initialize PaddleOCR: {exc}")
        _ocr_client = None
    return _ocr_client


def _run_ocr_from_url(image_url: str, cache: Optional[Dict[str, Any]] = None, driver=None,
                      referer: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Download image from URL and run OCR. Caches by URL to avoid duplicate downloads.
    Returns a serializable dict with full_text and line details.
    """
    if not image_url:
        return None

    if cache is not None and image_url in cache:
        return cache[image_url]

    ocr_client = _get_ocr_client()
    if ocr_client is None:
        if cache is not None:
            cache[image_url] = None
        return None

    tmp_path = None
    result_dict: Optional[Dict[str, Any]] = None
    try:
        content = _fetch_image_bytes(image_url, driver=driver, referer=referer)
        if content is None:
            raise RuntimeError("Could not fetch image for OCR")

        parsed = urlparse(image_url)
        suffix = (os.path.splitext(parsed.path)[1] or ".jpg").lower()
        allowed = {".jpg", ".jpeg", ".png", ".bmp", ".pdf"}

        if suffix not in allowed:
            try:
                from PIL import Image

                img = Image.open(io.BytesIO(content)).convert("RGB")
                with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_file:
                    img.save(tmp_file, format="PNG")
                    tmp_path = tmp_file.name
            except Exception as exc:
                print(f"Failed to convert image for OCR {image_url}: {exc}")
                with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_file:
                    tmp_file.write(content)
                    tmp_path = tmp_file.name
        else:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
                tmp_file.write(content)
                tmp_path = tmp_file.name

        result_dict = _run_ocr_core(ocr_client, tmp_path, source=image_url)
    except Exception as exc:
        print(f"OCR failed for {image_url}: {exc}")
        result_dict = None
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    if cache is not None:
        cache[image_url] = result_dict
    return result_dict


def _run_ocr_from_file(file_path: str, cache: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Run OCR on a local file; converts unsupported formats to PNG."""
    if not file_path or not os.path.exists(file_path):
        return None
    if os.path.getsize(file_path) == 0:
        print(f"OCR skipped empty file {file_path}")
        return None
    cache_key = os.path.abspath(file_path)
    if cache is not None and cache_key in cache:
        return cache[cache_key]

    ocr_client = _get_ocr_client()
    if ocr_client is None:
        if cache is not None:
            cache[cache_key] = None
        return None

    tmp_path = None
    result_dict: Optional[Dict[str, Any]] = None
    try:
        suffix = (os.path.splitext(file_path)[1] or ".jpg").lower()
        allowed = {".jpg", ".jpeg", ".png", ".bmp", ".pdf"}

        src_path = file_path
        if suffix not in allowed:
            try:
                from PIL import Image

                with open(file_path, "rb") as f:
                    content = f.read()
                img = Image.open(io.BytesIO(content)).convert("RGB")
                with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_file:
                    img.save(tmp_file, format="PNG")
                    src_path = tmp_file.name
                    tmp_path = tmp_file.name
            except Exception as exc:
                print(f"Failed to convert image for OCR {file_path}: {exc}")
                src_path = file_path
        else:
            src_path = file_path

        # If conversion failed but we still need a temp file fallback, ensure src_path exists
        if not os.path.exists(src_path):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_file:
                tmp_file.write(open(file_path, "rb").read())
                src_path = tmp_file.name
                tmp_path = tmp_file.name

        result_dict = _run_ocr_core(ocr_client, src_path, source=file_path)
    except Exception as exc:
        print(f"OCR failed for file {file_path}: {exc}")
        result_dict = None
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    if cache is not None:
        cache[cache_key] = result_dict
    return result_dict


def _run_ocr_core(ocr_client, img_path: str, source: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Run OCR with predict() when available, else fallback to ocr()."""
    def _parse_ocr_raw(ocr_raw) -> Dict[str, Any]:
        lines: List[Dict[str, Any]] = []
        texts: List[str] = []
        for page in ocr_raw or []:
            for entry in page or []:
                if not entry or len(entry) < 2:
                    continue
                box = entry[0]
                text_info = entry[1]
                text = ""
                score = None
                if isinstance(text_info, (list, tuple)):
                    if text_info:
                        text = text_info[0]
                    if len(text_info) > 1:
                        score = text_info[1]
                else:
                    text = str(text_info)
                if text:
                    texts.append(text)
                try:
                    normalized_box = [[float(pt[0]), float(pt[1])] for pt in box]
                except Exception:
                    normalized_box = []
                lines.append({
                    "text": text,
                    "score": float(score) if score is not None else None,
                    "box": normalized_box
                })
        return {"full_text": "\n".join(texts), "lines": lines}

    def _parse_predict_raw(pred_raw) -> Dict[str, Any]:
        lines: List[Dict[str, Any]] = []
        texts: List[str] = []
        for item in pred_raw or []:
            if hasattr(item, "boxes") and hasattr(item, "texts"):
                boxes = item.boxes
                texts_list = item.texts
                scores = getattr(item, "scores", [None] * len(texts_list))
                for b, t, s in zip(boxes, texts_list, scores):
                    texts.append(t)
                    try:
                        normalized_box = [[float(pt[0]), float(pt[1])] for pt in b]
                    except Exception:
                        normalized_box = []
                    lines.append({
                        "text": t,
                        "score": float(s) if s is not None else None,
                        "box": normalized_box
                    })
            elif hasattr(item, "text"):
                t = getattr(item, "text", "")
                s = getattr(item, "score", None)
                b = getattr(item, "box", []) or getattr(item, "boxes", [])
                texts.append(t)
                try:
                    normalized_box = [[float(pt[0]), float(pt[1])] for pt in b]
                except Exception:
                    normalized_box = []
                lines.append({
                    "text": t,
                    "score": float(s) if s is not None else None,
                    "box": normalized_box
                })
            elif hasattr(item, "res"):
                try:
                    r = item.res
                    rec_texts = r.get("rec_texts", []) if isinstance(r, dict) else []
                    rec_polys = r.get("rec_polys", []) if isinstance(r, dict) else []
                    rec_scores = r.get("rec_scores", []) if isinstance(r, dict) else []
                    for t, b, s in zip(rec_texts, rec_polys, rec_scores):
                        texts.append(t)
                        try:
                            normalized_box = [[float(pt[0]), float(pt[1])] for pt in b]
                        except Exception:
                            normalized_box = []
                        lines.append({
                            "text": t,
                            "score": float(s) if s is not None else None,
                            "box": normalized_box
                        })
                except Exception:
                    continue
            elif isinstance(item, dict) and "rec_texts" in item:
                rec_texts = item.get("rec_texts", [])
                rec_polys = item.get("rec_polys", [])
                rec_scores = item.get("rec_scores", [])
                for t, b, s in zip(rec_texts, rec_polys, rec_scores):
                    texts.append(t)
                    try:
                        normalized_box = [[float(pt[0]), float(pt[1])] for pt in b]
                    except Exception:
                        normalized_box = []
                    lines.append({
                        "text": t,
                        "score": float(s) if s is not None else None,
                        "box": normalized_box
                    })
        if not lines:
            return _parse_ocr_raw(None)
        return {"full_text": "\n".join(texts), "lines": lines}

    try:
        # Optional resize if image is too large for default paddle limits
        resize_path = None
        try:
            from PIL import Image
            with Image.open(img_path) as im:
                w, h = im.size
                max_side = 4000
                if max(w, h) > max_side:
                    scale = max_side / float(max(w, h))
                    new_size = (int(w * scale), int(h * scale))
                    im_resized = im.resize(new_size)
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_file:
                        im_resized.save(tmp_file, format="PNG")
                        resize_path = tmp_file.name
        except Exception:
            resize_path = None

        final_path = resize_path or img_path

        if hasattr(ocr_client, "predict"):
            try:
                pred_raw = ocr_client.predict(final_path)
                parsed = _parse_predict_raw(pred_raw)
                return {"image_url": source or img_path, **parsed}
            except Exception as exc:
                print(f"OCR predict() failed for {source or img_path}: {exc}")
        ocr_raw = ocr_client.ocr(final_path)
        parsed = _parse_ocr_raw(ocr_raw)
        return {"image_url": source or img_path, **parsed}
    except Exception as exc:
        print(f"OCR core failed for {source or img_path}: {exc}")
        return None
    finally:
        try:
            if resize_path and os.path.exists(resize_path):
                os.remove(resize_path)
        except Exception:
            pass
def _get_text_js(el) -> str:
    """优先用 DOM 属性取文本，避免 Selenium .text 为空的问题。"""
    try:
        text = el.get_attribute("textContent") or ""
        text = text.strip()
        if text:
            return text
    except Exception:
        pass

    try:
        text = el.get_attribute("innerText") or ""
        return text.strip()
    except Exception:
        return ""

def _refind_sku_container(driver, wait):
    """Re-find the SKU container after DOM updates."""
    for selector in [
        'div[class*="skuWrapper"]',
        'div[class*="sku"]',
        'div[class*="Sku"]',
        '.tb-sku',
        '.sku-inner'
    ]:
        try:
            return wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
        except TimeoutException:
            continue
    return None

def _find_size_sku_item(sku_container):
    """Find the size SKU item within the container."""
    sku_items = sku_container.find_elements(By.CSS_SELECTOR, '[class*="skuItem"]')
    label_candidates = ("尺码", "尺寸", "Size")
    for item in sku_items:
        for cand in label_candidates:
            try:
                item.find_element(
                    By.XPATH,
                    f'.//*[contains(@class,"labelWrap")]//*[normalize-space()="{cand}" or @title="{cand}"]'
                )
                return item
            except NoSuchElementException:
                pass
    return None


def extract_price_info(driver, timeout: int = 15) -> dict[str, str]:
    wait = WebDriverWait(driver, timeout)
    price_info: dict[str, str] = {}

    price_wrap = wait.until(
        EC.presence_of_element_located((By.CSS_SELECTOR, '[class*="priceWrap--"]'))
    )

    # 券后：symbol + number
    try:
        hl = price_wrap.find_element(By.CSS_SELECTOR, '[class*="highlightPrice--"]')
        symbol_el = hl.find_element(By.CSS_SELECTOR, '[class*="symbol--"]')
        value_el = hl.find_element(By.CSS_SELECTOR, '[class*="text--"]')

        symbol = _get_text_js(symbol_el)
        value = _get_text_js(value_el)

        if symbol and value:
            price_info["coupon_price"] = f"{symbol}{value}"
    except Exception:
        pass

    # 优惠前：可能是两个 text--，第一个是 ¥，第二个是数字
    try:
        sub = price_wrap.find_element(By.CSS_SELECTOR, '[class*="subPrice--"]')
        text_els = sub.find_elements(By.CSS_SELECTOR, '[class*="text--"]')
        parts = [_get_text_js(e) for e in text_els]
        joined = "".join([p for p in parts if p])

        m = re.search(r"¥\s*(\d+(?:\.\d+)?)", joined)
        if m:
            price_info["original_price"] = f"¥{m.group(1)}"
    except Exception:
        pass

    # 已售
    try:
        sales_el = price_wrap.find_element(By.CSS_SELECTOR, '[class*="salesDesc--"]')
        sales_text = _get_text_js(sales_el)
        if sales_text:
            price_info["sales"] = sales_text.replace("\n", " ").strip()
    except Exception:
        pass

    return price_info

def scrape_single_product(driver, product_url):
    """
    Scrapes a single product page for all its style variations, including
    the name, image, and available sizes for each style.
    Also scrapes product details like reviews and parameters.
    """
    print(f"Navigating to product page: {product_url}")
    driver.get(product_url)

    # Wait a bit for page to fully load
    time.sleep(3)

    # Scroll down to load the detail section
    print("Scrolling to load product details...")
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(2)

    all_styles_data = []
    ocr_cache: Dict[str, Any] = {}

    try:
        # Wait for the SKU component to be ready - try multiple possible selectors
        wait = WebDriverWait(driver, 20)
        sku_container = None
        sku_selectors = [
            'div[class*="skuWrapper"]',
            'div[class*="sku"]',
            'div[class*="Sku"]',
            '.tb-sku',
            '.sku-inner'
        ]

        for selector in sku_selectors:
            try:
                sku_container = wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                print(f"Found SKU container with selector: {selector}")
                break
            except TimeoutException:
                continue

        if not sku_container:
            print("Could not find SKU container with any known selector.")
            # Debug: print page source to file
            with open("debug_page_source.html", "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            print("Page source saved to debug_page_source.html for inspection.")
            return None

        # Try to find style/color options with multiple approaches
        style_elements = []

        # Method 1: Look for "颜色分类" (Color/Style) label - use more reliable selectors
        try:
            # Find the skuItem that contains "颜色分类"
            color_sku_item = None
            sku_items = sku_container.find_elements(By.CSS_SELECTOR, '[class*="skuItem"]')

            for item in sku_items:
                try:
                    # Look for span with title="颜色分类" or containing "颜色" text
                    # Try multiple possible label texts (e.g. 颜色分类, 颜色, 口味, 款式, 风格, 规格)
                    label_span = None
                    label_candidates = ["颜色分类", "颜色", "口味", "款式", "风格", "规格"]
                    for cand in label_candidates:
                        try:
                            label_span = item.find_element(By.XPATH, f'.//span[@title="{cand}" or contains(text(), "{cand}")]')
                            break
                        except NoSuchElementException:
                            continue
                    if label_span:
                        color_sku_item = item
                        print(f"Found color SKU item with label: {label_span.text}")
                        break
                except NoSuchElementException:
                    continue

            if color_sku_item:
                # Find all valueItem elements in the content area
                # First find the skuValueWrap which contains all the options
                sku_value_wrap = color_sku_item.find_element(By.CSS_SELECTOR, '[class*="skuValueWrap"]')
                # Then find the content div, and finally all valueItem elements within it
                content_div = sku_value_wrap.find_element(By.CSS_SELECTOR, '[class*="content"]')
                # Find only direct child valueItem div elements to avoid duplicates
                # Use XPath to find direct children
                all_value_items = content_div.find_elements(By.XPATH, './div[contains(@class, "valueItem")]')
                print(f"Debug: XPath found {len(all_value_items)} valueItem divs")

                # If XPath doesn't work, try CSS selector as fallback
                if len(all_value_items) == 0:
                    print("Debug: XPath failed, trying CSS selector...")
                    all_value_items = content_div.find_elements(By.CSS_SELECTOR, 'div.valueItem--smR4pNt4')
                    print(f"Debug: CSS selector found {len(all_value_items)} elements")

                    # If still nothing, try finding all divs
                    if len(all_value_items) == 0:
                        all_divs = content_div.find_elements(By.TAG_NAME, 'div')
                        print(f"Debug: Found {len(all_divs)} total divs in content")
                        for i, div in enumerate(all_divs):
                            classes = div.get_attribute('class')
                            print(f"  - Div {i}: class={classes}")

                # All elements are already valueItem divs, no need to filter
                style_elements = all_value_items

                # Debug: Print the class names to understand what we're getting
                print(f"Method 1 found {len(style_elements)} style elements")
                for i, elem in enumerate(style_elements[:3]):  # Only print first 3 to avoid spam
                    print(f"  - Element {i}: class={elem.get_attribute('class')}, text={elem.text[:30]}")
            else:
                raise NoSuchElementException("Could not find color SKU item")
        except (NoSuchElementException, Exception) as e:
            print(f"Method 1 failed: {str(e)}")
            pass

        # Method 2: Look for any elements with SKU property names
        if not style_elements:
            try:
                style_elements = sku_container.find_elements(By.CSS_SELECTOR, 'div[data-property="颜色"], div[data-property="风格"], div[data-sku-prop]')
                print(f"Method 2 found {len(style_elements)} style elements")
            except Exception as e:
                print(f"Method 2 failed: {str(e)}")
                pass

        # Method 3: Look for clickable elements in SKU area
        if not style_elements:
            try:
                style_elements = sku_container.find_elements(By.CSS_SELECTOR, 'a[href*="sku"], .sku-item a, .tb-prop a')
                print(f"Method 3 found {len(style_elements)} style elements")
            except Exception as e:
                print(f"Method 3 failed: {str(e)}")
                pass

        # Method 4: Look for any elements that might be style options
        if not style_elements:
            try:
                # Find all clickable elements within SKU that might be style options
                all_clickable = sku_container.find_elements(By.CSS_SELECTOR, 'a, li[onclick], div[onclick], [data-sku-id]')
                # Filter out size options (usually contain numbers or size words)
                size_keywords = ['尺码', 'size', '均码', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL']
                style_elements = [elem for elem in all_clickable
                                if not any(keyword in elem.text.upper() for keyword in size_keywords)
                                and elem.text.strip()]
                print(f"Method 4 found {len(style_elements)} potential style elements")
            except Exception as e:
                print(f"Method 4 failed: {str(e)}")
                pass

        if not style_elements:
            print("No style options found with any method.")
            # Debug: save SKU container HTML
            sku_html = sku_container.get_attribute('outerHTML') or str(sku_container.get_attribute('innerHTML'))
            with open("debug_sku_container.html", "w", encoding="utf-8") as f:
                f.write(sku_html)
            print("SKU container HTML saved to debug_sku_container.html for inspection.")
            return None

        print(f"Found {len(style_elements)} style(s). Starting iteration...")

        for index, style_element in enumerate(style_elements):
            style_data = {"style_name": "N/A", "image_url": "N/A", "available_sizes": []}

            # Check style availability first (before clicking)
            data_disabled = style_element.get_attribute('data-disabled') or 'false'
            style_is_available = data_disabled == 'false'
            style_data["available"] = style_is_available

            # 1. Get Style Name - based on the DOM structure we analyzed
            style_name = "N/A"
            try:
                # From the DOM analysis, the style name is in a span with class="valueItemText"
                style_name_tag = style_element.find_element(By.CSS_SELECTOR, 'span[class*="valueItemText"]')
                # The title attribute contains the full name
                style_name = style_name_tag.get_attribute('title')
                if not style_name:
                    # If no title, use the text content
                    style_name = style_name_tag.text.strip()

                # Also try to get the image URL if available
                try:
                    img_tag = style_element.find_element(By.CSS_SELECTOR, 'img[class*="valueItemImg"]')
                    style_data["image_url"] = img_tag.get_attribute('src')
                except Exception:
                    pass

                style_data["style_name"] = style_name
            except Exception as e:
                print(f"  - Could not find name for style {index + 1}: {str(e)}")
                # Still continue even if we can't find the name
                style_data["style_name"] = f"Style_{index + 1}"

            print(f"\nProcessing Style {index + 1}: {style_data['style_name']} ({'有货' if style_is_available else '缺货'})")

            # 2. Click the style to trigger updates (only if available)
            initial_img_src = None
            # Define main image selectors here to make them available in later code blocks
            main_img_selectors = [
                '#mainPicImageEl',  # Original ID selector
                '[id*="mainPic"]',  # Partial ID match
                'img[class*="mainPic"]',  # Class containing mainPic
                '.pic-view img',  # Common picture viewer structure
                '.pic img:first',  # First image in pic container
                '[class*="pic--"] img:first',  # CSS module pic container
                '[class*="image--"] img:first',  # CSS module image container
            ]

            if style_is_available:
                try:
                    # Get the current main image URL to detect changes later
                    # Try multiple possible selectors for the main image
                    main_img = None
                    for selector in main_img_selectors:
                        try:
                            main_img = driver.find_element(By.CSS_SELECTOR, selector)
                            initial_img_src = main_img.get_attribute('src')
                            print(f"  - Found main image with selector: {selector}")
                            break
                        except NoSuchElementException:
                            continue

                    driver.execute_script("arguments[0].click();", style_element)
                except Exception as e:
                    print(f"  - Could not click on style '{style_data['style_name']}'. Error: {e}")
                    # Continue even if click fails
            else:
                print("  - Style is sold out, skipping click")

            # 3. Wait for the main image to update and get the new URL (only if we clicked)
            if style_is_available and initial_img_src:
                try:
                    # Wait a moment for the image to load
                    time.sleep(0.5)
                    # Try to find the main image element again with multiple selectors
                    current_img_src = None
                    for selector in main_img_selectors:
                        try:
                            main_img = driver.find_element(By.CSS_SELECTOR, selector)
                            current_img_src = main_img.get_attribute('src')
                            break
                        except NoSuchElementException:
                            continue

                    if current_img_src and current_img_src != initial_img_src:
                        style_data["image_url"] = current_img_src
                        print("  - Image updated successfully.")
                    else:
                        # If we already got the image from the thumbnail, use that
                        if style_data.get("image_url") == "N/A":
                            style_data["image_url"] = current_img_src or initial_img_src
                        print("  - Using current image URL.")
                except Exception as e:
                    print(f"  - Error getting main image: {e}")
                    # Use the initial image as fallback
                    if style_data.get("image_url") == "N/A":
                        style_data["image_url"] = initial_img_src

            # 4. Get sizes for the current style with their availability
            sizes = []
            try:
                # Key fix: Re-find SKU container after clicking style to avoid stale reference
                sku_container = _refind_sku_container(driver, wait)
                if not sku_container:
                    raise RuntimeError("Failed to re-find sku_container after style click")

                size_sku_item = _find_size_sku_item(sku_container)
                if not size_sku_item:
                    print("  - Could not find size SKU section")
                    style_data["sizes"] = []
                else:
                    sku_value_wrap = size_sku_item.find_element(By.CSS_SELECTOR, '[class*="skuValueWrap"]')
                    content_div = sku_value_wrap.find_element(By.CSS_SELECTOR, '[class*="content--"], [class*="content"]')

                    # Key fix: Use descendant find (//) instead of direct child (./) for robustness
                    size_elements = content_div.find_elements(By.XPATH, './/div[contains(@class, "valueItem")]')
                    print(f"  - Debug: Found {len(size_elements)} size elements")

                    for size_element in size_elements:
                        try:
                            size_name_tag = size_element.find_element(By.CSS_SELECTOR, 'span[class*="valueItemText"]')
                            size_name = size_name_tag.get_attribute('title') or _get_text_js(size_name_tag)
                        except Exception:
                            size_name = _get_text_js(size_element) or size_element.get_attribute("title") or ""

                        size_name = (size_name or "").strip()
                        if not size_name:
                            continue

                        size_data_disabled = size_element.get_attribute('data-disabled') or 'false'
                        size_is_available = (size_data_disabled == 'false')

                        # Avoid duplicates
                        if not any(s['name'] == size_name for s in sizes):
                            sizes.append({
                                "name": size_name,
                                "available": size_is_available
                            })
                            print(f"    - Size {size_name}: {'有货' if size_is_available else '缺货'}")

                    style_data["sizes"] = sizes
                    available_size_names = [s['name'] for s in sizes if s['available']]
                    print(f"  - Available sizes: {available_size_names}")
            except Exception as e:
                print(f"  - Error getting sizes: {e}")
                style_data["sizes"] = []

            # Remove the old available_sizes field if it exists
            if "available_sizes" in style_data:
                del style_data["available_sizes"]

            all_styles_data.append(style_data)
            time.sleep(0.5) # Small delay between clicks

    except (TimeoutException, NoSuchElementException) as e:
        print(f"Error finding essential SKU components on the page. Please check the URL. Error: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None

    # Extract product title, shop info, and other details
    product_title = ""
    shop_info = {}
    shipping_info = {}
    price_info = {}
    coupon_info = []

    try:
        # Extract product title
        title_element = driver.find_element(By.CSS_SELECTOR, '[class*="mainTitle--"]')
        product_title = title_element.get_attribute('title') or title_element.text.strip()
        print(f"Product title: {product_title}")
    except Exception as e:
        print(f"Error extracting product title: {e}")
        # Fallback: try to get title from page title
        try:
            product_title = driver.title.split(' - ')[0]
        except:
            product_title = "Unknown Product"

    try:
        # Extract shop information
        shop_header = driver.find_element(By.CSS_SELECTOR, '[class*="shopHeader--"]')

        # Shop name
        try:
            shop_name_elem = shop_header.find_element(By.CSS_SELECTOR, '[class*="shopName--"]')
            shop_info['name'] = shop_name_elem.get_attribute('title') or shop_name_elem.text.strip()
        except:
            shop_info['name'] = "Unknown Shop"

        # Shop URL
        try:
            shop_link = shop_header.find_element(By.CSS_SELECTOR, 'a[href*="shop"]')
            shop_url = shop_link.get_attribute('href')
            if shop_url and shop_url.startswith('//'):
                shop_url = 'https:' + shop_url
            shop_info['url'] = shop_url
        except:
            shop_info['url'] = ""

        # Shop rating
        try:
            rating_elem = shop_header.find_element(By.CSS_SELECTOR, '[class*="starNum--"]')
            shop_info['rating'] = rating_elem.text.strip()
        except:
            shop_info['rating'] = ""

        # Good review rate
        try:
            review_rate_elems = shop_header.find_elements(By.XPATH, ".//*[contains(text(), '好评率')]")
            for elem in review_rate_elems:
                if '好评率' in elem.text:
                    shop_info['good_review_rate'] = elem.text.strip()
                    break
        except:
            shop_info['good_review_rate'] = ""

        print(f"Shop info: {shop_info}")
    except Exception as e:
        print(f"Error extracting shop info: {e}")
        shop_info = {
            'name': "Unknown Shop",
            'url': "",
            'rating': "",
            'good_review_rate': ""
        }

    # Extract shipping information
    try:
        shipping_container = driver.find_element(By.CSS_SELECTOR, '[class*="SecondCard--"]')
        # Get delivery info
        delivery_elem = shipping_container.find_element(By.CSS_SELECTOR, '[class*="DomesticDelivery--"]')
        if delivery_elem:
            shipping_elem = delivery_elem.find_element(By.CSS_SELECTOR, '[class*="shipping--"]')
            if shipping_elem:
                shipping_info['delivery'] = shipping_elem.text.strip()

            freight_elem = delivery_elem.find_element(By.CSS_SELECTOR, '[class*="freight--"]')
            if freight_elem:
                shipping_info['freight'] = freight_elem.text.strip()

            addr_elem = delivery_elem.find_element(By.CSS_SELECTOR, '[class*="deliveryAddrWrap--"] span')
            if addr_elem:
                shipping_info['delivery_address'] = addr_elem.text.strip()

        # Get guarantee info
        guarantee_elem = shipping_container.find_element(By.CSS_SELECTOR, '[class*="GuaranteeInfo--"]')
        if guarantee_elem:
            guarantee_texts = guarantee_elem.find_elements(By.CSS_SELECTOR, '[class*="guaranteeText--"]')
            shipping_info['guarantees'] = [g.text.strip() for g in guarantee_texts if g.text.strip()]
    except Exception as e:
        print(f"Error extracting shipping info: {e}")
    # Extract price information
    try:
        print("Starting price extraction...")
        price_info = extract_price_info(driver)
        print(f"Final price info: {price_info}")
    except Exception as e:
        print(f"Error extracting price info: {e}")
        price_info = {}


    # Extract coupon information
    try:
        coupon_container = driver.find_element(By.CSS_SELECTOR, '[class*="couponInfoArea--"]')
        coupon_list = coupon_container.find_elements(By.CSS_SELECTOR, '[class*="couponWrap--"]')
        for coupon in coupon_list:
            coupon_elem = coupon.find_element(By.CSS_SELECTOR, '[class*="couponText--"]')
            if coupon_elem:
                coupon_info.append({
                    'title': coupon_elem.get_attribute('title'),
                    'text': coupon_elem.text.strip()
                })
    except Exception as e:
        print(f"Error extracting coupon info: {e}")

    # Aggregate OCR text from style main images
    main_image_ocr_texts = []
    for style in all_styles_data:
        ocr_block = style.get("ocr") if isinstance(style, dict) else None
        if ocr_block and ocr_block.get("full_text"):
            main_image_ocr_texts.append(ocr_block["full_text"])

    details_data = scrape_product_details(driver, ocr_cache=ocr_cache, product_url=product_url)
    if main_image_ocr_texts:
        # Deduplicate while preserving order
        seen = set()
        unique_texts = []
        for text in main_image_ocr_texts:
            if text not in seen:
                seen.add(text)
                unique_texts.append(text)
        details_data["main_images_ocr_text"] = "\n".join(unique_texts)

    # Prepare final result with all data
    result = {
        "product_info": {
            "title": product_title,
            "url": product_url,
            "shop": shop_info,
            "shipping": shipping_info,
            "price": price_info,
            "coupons": coupon_info
        },
        "styles": all_styles_data,
        "product_details": details_data
    }

    return result

def scrape_product_details(driver, ocr_cache: Optional[Dict[str, Any]] = None, product_url: Optional[str] = None):
    """Scrape product details including reviews, parameters and image details"""
    details = {
        "reviews": [],
        "parameters": {},
        "parameters_raw": "",  # Store raw DOM for parameters
        "image_details": [],
        "image_details_raw": "",  # Store raw DOM for image details
        "image_details_ocr": [],
        "main_images_ocr_text": "",
        "detail_images_ocr_text": ""
    }

    try:
        # Find the detail info container
        detail_container = driver.find_element(By.CSS_SELECTOR, '[class*="detailInfo"]')

        # 1. Get Reviews
        try:
            # Find review comments
            review_elements = detail_container.find_elements(By.CSS_SELECTOR, '[class*="Comment--"]')

            for review_elem in review_elements[:5]:  # Limit to first 5 reviews
                try:
                    # Get user name
                    user_name_elem = review_elem.find_element(By.CSS_SELECTOR, '[class*="userName--"]')
                    user_name = user_name_elem.text.strip() if user_name_elem else "Anonymous"

                    # Get date and purchase info
                    meta_elem = review_elem.find_element(By.CSS_SELECTOR, '[class*="meta--"]')
                    meta_info = meta_elem.text.strip() if meta_elem else ""

                    # Get review content
                    content_elem = review_elem.find_element(By.CSS_SELECTOR, '[class*="content--"]')
                    content = content_elem.get_attribute('title') or content_elem.text.strip()

                    # Get images if available
                    images = []
                    try:
                        img_elements = review_elem.find_elements(By.CSS_SELECTOR, '[class*="photo--"] img')
                        for img in img_elements:
                            img_src = img.get_attribute('src')
                            if img_src:
                                images.append(img_src)
                    except Exception:
                        pass

                    details["reviews"].append({
                        "user": user_name,
                        "meta": meta_info,
                        "content": content,
                        "images": images
                    })
                except Exception as e:
                    print(f"  - Error extracting review: {str(e)}")
                    continue
        except Exception as e:
            print(f"  - Error getting reviews: {str(e)}")

        # 2. Get Product Parameters
        params_area = None
        try:
            # Method 1: Look for paramsInfoArea class within detailInfo
            param_elements = []

            # First try to find paramsInfoArea directly in the page
            try:
                params_area = driver.find_element(By.CSS_SELECTOR, '[class*="paramsInfoArea"]')
                print("  - Found paramsInfoArea directly in page")
                # Save raw DOM for parameters
                details["parameters_raw"] = params_area.get_attribute('outerHTML')
            except:
                # Try within detail_container
                try:
                    params_area = detail_container.find_element(By.CSS_SELECTOR, '[class*="paramsInfoArea"]')
                    print("  - Found paramsInfoArea within detail_container")
                    # Save raw DOM for parameters
                    details["parameters_raw"] = params_area.get_attribute('outerHTML')
                except:
                    pass

            if params_area:
                # Get both emphasis and general params
                emphasis_params = params_area.find_elements(By.CSS_SELECTOR, '[class*="emphasisParamsInfoItem--"]')
                general_params = params_area.find_elements(By.CSS_SELECTOR, '[class*="generalParamsInfoItem--"]')
                param_elements = emphasis_params + general_params
                print(f"  - Found {len(emphasis_params)} emphasis params and {len(general_params)} general params")
            else:
                # Method 2: Look for data-tabindex elements containing "产品参数"
                try:
                    param_tabs = detail_container.find_elements(By.CSS_SELECTOR, '[data-tabindex]')
                    for tab in param_tabs:
                        try:
                            tab_title = tab.find_element(By.CSS_SELECTOR, '[class*="tabTitle--"]')
                            if tab_title and ("产品参数" in tab_title.text or "参数信息" in tab_title.text):
                                param_elements = tab.find_elements(By.CSS_SELECTOR, '[class*="paramsInfoItem--"]')
                                print(f"  - Found params via tab '{tab_title.text}': {len(param_elements)} items")
                                # Save raw DOM for this tab
                                details["parameters_raw"] = tab.get_attribute('outerHTML')
                                break
                        except:
                            continue
                except:
                    pass

            # If still no params, try direct search for parameter items
            if not param_elements:
                try:
                    # Look for any element containing parameter info
                    param_elements = driver.find_elements(By.CSS_SELECTOR, '[class*="emphasisParamsInfoItem--"], [class*="generalParamsInfoItem--"]')
                    print(f"  - Found {len(param_elements)} params via direct search")
                    # Save all found elements as raw DOM
                    if param_elements:
                        raw_html = ""
                        for elem in param_elements:
                            raw_html += elem.get_attribute('outerHTML') + "\n"
                        details["parameters_raw"] = raw_html
                except:
                    pass

            # Extract parameters with improved selectors
            for param_elem in param_elements:
                try:
                    # Try multiple selector patterns for title and value
                    title_elem = None
                    subtitle_elem = None
                    class_attr = param_elem.get_attribute('class') or ''
                    is_emphasis = 'emphasisParamsInfoItem' in class_attr  # Emphasis block shows value first, label second

                    # Pattern 1: ItemTitle and ItemSubTitle
                    try:
                        title_elem = param_elem.find_element(By.CSS_SELECTOR, '[class*="ItemTitle--"]')
                        subtitle_elem = param_elem.find_element(By.CSS_SELECTOR, '[class*="ItemSubTitle--"]')
                    except:
                        pass

                    # Pattern 2: InfoItemTitle and InfoItemSubTitle
                    if not title_elem or not subtitle_elem:
                        try:
                            title_elem = param_elem.find_element(By.CSS_SELECTOR, '[class*="InfoItemTitle--"]')
                            subtitle_elem = param_elem.find_element(By.CSS_SELECTOR, '[class*="InfoItemSubTitle--"]')
                        except:
                            pass

                    # Pattern 3: Direct child elements
                    if not title_elem or not subtitle_elem:
                        try:
                            # Get all spans and assume first is title, second is value
                            spans = param_elem.find_elements(By.TAG_NAME, 'span')
                            if len(spans) >= 2:
                                title_elem = spans[0]
                                subtitle_elem = spans[1]
                        except:
                            pass

                    if title_elem and subtitle_elem:
                        title_text = (title_elem.get_attribute('title') or _get_text_js(title_elem) or "").strip()
                        subtitle_text = (subtitle_elem.get_attribute('title') or _get_text_js(subtitle_elem) or "").strip()

                        # Emphasis cards put the value in the "title" element and the label in the "subtitle" element
                        if is_emphasis:
                            param_name, param_value = subtitle_text, title_text
                        else:
                            param_name, param_value = title_text, subtitle_text

                        # Fallback: if one side is empty, try the other order
                        if (not param_name or not param_value) and title_text and subtitle_text:
                            param_name, param_value = param_value, param_name

                        if param_name and param_value:
                            details["parameters"][param_name] = param_value
                            print(f"    - Extracted: {param_name} = {param_value}")
                except Exception as e:
                    print(f"    - Error extracting parameter: {str(e)}")
                    continue

            print(f"  - Total parameters extracted: {len(details['parameters'])}")
            print(f"  - Raw parameters DOM saved: {len(details['parameters_raw'])} characters")
        except Exception as e:
            print(f"  - Error getting parameters: {str(e)}")

        # 3. Get Image Details from 图文详情 tab
        try:
            # Method 1: Try to find elements with data-tabindex attribute
            image_tab = None

            # First try to find tabs with data-tabindex
            tabs = driver.find_elements(By.CSS_SELECTOR, '[data-tabindex]')

            for tab in tabs:
                try:
                    # Look for tabDetailItemTitle class containing "图文详情"
                    tab_title_elements = tab.find_elements(By.CSS_SELECTOR, '[class*="tabDetailItemTitle"]')
                    for title_elem in tab_title_elements:
                        if "图文详情" in title_elem.text:
                            image_tab = tab
                            print(f"  - Found 图文详情 tab (method 1)")
                            break
                    if image_tab:
                        break
                except Exception:
                    continue

            # Method 2: If not found, try searching the entire page
            if not image_tab:
                try:
                    # Look for any element containing "图文详情" text
                    elements_with_text = driver.find_elements(By.XPATH, "//*[contains(text(), '图文详情')]")
                    for elem in elements_with_text:
                        # Find the parent container with data-tabindex
                        parent = elem
                        for _ in range(5):  # Go up at most 5 levels
                            try:
                                parent = parent.find_element(By.XPATH, '..')
                                if parent.get_attribute('data-tabindex'):
                                    image_tab = parent
                                    print(f"  - Found 图文详情 tab (method 2)")
                                    break
                            except:
                                break
                        if image_tab:
                            break
                except Exception as e:
                    print(f"  - Method 2 failed: {str(e)}")

            if image_tab:
                try:
                    # Save the entire tab's raw DOM first
                    details["image_details_raw"] = image_tab.get_attribute('outerHTML')

                    # Get the desc-root container within the tab
                    desc_root = image_tab.find_element(By.CSS_SELECTOR, '[class*="desc-root"]')

                    # Find all images - try multiple selectors
                    img_selectors = [
                        'img[class*="descV8-singleImage-image"]',
                        '.descV8-singleImage-image',
                        'img[class*="lazyload"]',
                        'img[data-src]',
                        'img[src*="alicdn.com"]'
                    ]

                    all_imgs = []
                    for selector in img_selectors:
                        try:
                            img_elements = desc_root.find_elements(By.CSS_SELECTOR, selector)
                            all_imgs.extend(img_elements)
                            print(f"    - Selector '{selector}' found {len(img_elements)} images")
                        except Exception:
                            pass

                    # Extract image URLs
                    for img in all_imgs:
                        # Try both src and data-src attributes
                        img_src = img.get_attribute('data-src') or img.get_attribute('src')
                        if img_src and img_src not in details["image_details"]:
                            # Skip placeholder images
                            if 'g.alicdn.com/s.gif' in img_src:
                                # Check if this is a lazyloaded image
                                img_src = img.get_attribute('data-src')
                                if not img_src:
                                    continue

                            # Convert relative URLs to absolute
                            if img_src.startswith('//'):
                                img_src = 'https:' + img_src
                            elif img_src.startswith('/'):
                                img_src = 'https://img.alicdn.com' + img_src

                            details["image_details"].append(img_src)
                            print(f"    - Added image: {img_src[:80]}...")

                    print(f"  - Found {len(details['image_details'])} images in 图文详情")
                    print(f"  - Raw image details DOM saved: {len(details['image_details_raw'])} characters")

                except Exception as e:
                    print(f"  - Error extracting images from tab: {str(e)}")
                    # Still save the tab DOM even if extraction fails
                    try:
                        details["image_details_raw"] = image_tab.get_attribute('outerHTML')
                        print(f"  - Saved raw DOM despite extraction error")
                    except:
                        pass
            else:
                print("  - 图文详情 tab not found")
                # Debug: try to save all tabs to see what's available
                try:
                    all_tabs = driver.find_elements(By.CSS_SELECTOR, '[data-tabindex]')
                    print(f"  - Debug: Found {len(all_tabs)} tabs with data-tabindex")
                    for i, tab in enumerate(all_tabs[:3]):  # Only check first 3
                        try:
                            title_text = tab.text[:50] if tab.text else "No text"
                            print(f"    - Tab {i}: {title_text}")
                        except:
                            pass
                except:
                    pass
        except Exception as e:
            print(f"  - Error getting image details: {str(e)}")

    except Exception as e:
        print(f"Error scraping product details: {str(e)}")

    return details


def scrape_product_data(product_url: str, driver=None, save_to_file: bool = False,
                        output_folder: Optional[str] = None,
                        close_driver: bool = False) -> Optional[ProductData]:
    """
    Entry point for other modules to scrape product data.

    Args:
        product_url: The product URL to scrape
        driver: Optional existing WebDriver instance. If None, creates a new one.
        save_to_file: Whether to save the scraped data to files
        output_folder: Optional output folder path. If None and save_to_file is True,
                      creates a timestamped folder in scraped_data/
        close_driver: Whether to close the driver after scraping. Only used when driver is provided.
                     If driver is None (created internally), it will always be closed.

    Returns:
        ProductData object with all scraped information, or None if scraping failed
    """
    # Create driver if not provided
    driver_created = False
    if driver is None:
        driver = setup_driver()
        driver_created = True
        # Login period
        print("Opening Taobao/Tmall. Please log in manually if required within 5 seconds.")
        driver.get("https://www.taobao.com")
        time.sleep(5)
        print("Login period over. Starting scrape...")

    try:
        # Scrape the product
        result_dict = scrape_single_product(driver, product_url)

        if not result_dict:
            print(f"Failed to scrape product: {product_url}")
            return None

        # Convert dictionary to ProductData object
        product_data = _dict_to_product_data(result_dict)

        # Save to file if requested
        if save_to_file:
            _save_product_data_to_files(product_data, result_dict, output_folder, driver=driver)

        return product_data

    finally:
        # Close driver only if we created it OR if close_driver is explicitly True
        if driver_created or close_driver:
            driver.quit()


def _dict_to_ocr_result(data: Dict[str, Any]) -> OCRResult:
    """Convert a raw OCR dict to OCRResult dataclass."""
    lines = []
    for line in data.get("lines", []):
        try:
            lines.append(OCRTextLine(
                text=line.get("text", ""),
                score=line.get("score"),
                box=line.get("box", [])
            ))
        except Exception:
            continue
    return OCRResult(
        image_url=data.get("image_url", ""),
        full_text=data.get("full_text", ""),
        lines=lines
    )


def _dict_to_product_data(data: Dict[str, Any]) -> ProductData:
    """Convert dictionary data to ProductData object."""
    # Convert product info
    product_info_dict = data['product_info']

    # Handle shop info with defaults for missing fields
    shop_dict = product_info_dict['shop']
    shop_info = ShopInfo(
        name=shop_dict.get('name', 'Unknown Shop'),
        url=shop_dict.get('url', ''),
        rating=shop_dict.get('rating', ''),
        good_review_rate=shop_dict.get('good_review_rate', '')
    )

    shipping_info = ShippingInfo(**product_info_dict.get('shipping', {}))
    price_info = PriceInfo(**product_info_dict.get('price', {}))
    coupons = [CouponInfo(**c) for c in product_info_dict.get('coupons', [])]

    product_info = ProductInfo(
        title=product_info_dict['title'],
        url=product_info_dict['url'],
        shop=shop_info,
        shipping=shipping_info,
        price=price_info,
        coupons=coupons
    )

    # Convert styles
    styles = []
    for style_dict in data['styles']:
        sizes = [SizeInfo(**size_dict) for size_dict in style_dict.get('sizes', [])]
        ocr_result = None
        if style_dict.get('ocr'):
            try:
                ocr_result = _dict_to_ocr_result(style_dict['ocr'])
            except Exception:
                ocr_result = None
        style = StyleInfo(
            style_name=style_dict['style_name'],
            image_url=style_dict['image_url'],
            available=style_dict.get('available', True),
            sizes=sizes,
            ocr=ocr_result
        )
        styles.append(style)

    # Convert product details
    details_dict = data['product_details']
    reviews = [ReviewInfo(**review) for review in details_dict.get('reviews', [])]
    image_detail_ocr = []
    for ocr_item in details_dict.get('image_details_ocr', []):
        try:
            image_detail_ocr.append(_dict_to_ocr_result(ocr_item))
        except Exception:
            continue
    product_details = ProductDetails(
        reviews=reviews,
        parameters=details_dict.get('parameters', {}),
        parameters_raw=details_dict.get('parameters_raw', ''),
        image_details=details_dict.get('image_details', []),
        image_details_raw=details_dict.get('image_details_raw', ''),
        image_details_ocr=image_detail_ocr,
        main_images_ocr_text=details_dict.get('main_images_ocr_text', ''),
        detail_images_ocr_text=details_dict.get('detail_images_ocr_text', '')
    )

    return ProductData(
        product_info=product_info,
        styles=styles,
        product_details=product_details
    )


def _browser_fetch_image(driver, url: str) -> Optional[bytes]:
    """Fetch image via browser context (with cookies) and return bytes."""
    if driver is None:
        return None
    try:
        script = """
        const url = arguments[0];
        const callback = arguments[arguments.length - 1];
        fetch(url, {credentials: 'include'})
          .then(resp => resp.arrayBuffer())
          .then(buf => {
            const bytes = new Uint8Array(buf);
            let binary = '';
            const chunk = 8192;
            for (let i = 0; i < bytes.length; i += chunk) {
              const sub = bytes.subarray(i, i + chunk);
              binary += String.fromCharCode.apply(null, sub);
            }
            const base64 = btoa(binary);
            callback({ ok: true, base64 });
          })
          .catch(err => callback({ ok: false, error: String(err) }));
        """
        result = driver.execute_async_script(script, url)
        if isinstance(result, dict) and result.get("ok") and result.get("base64"):
            return base64.b64decode(result["base64"])
    except Exception as exc:
        print(f"Browser fetch failed for {url}: {exc}")
    return None


def _dom_fetch_image_new_tab(driver, url: str) -> Optional[bytes]:
    """
    Open a new tab, load the image URL, and尝试通过 Tampermonkey 暴露的 __GET_IMAGE_BASE64__ 获取。
    若未注入脚本则退回 canvas/fetch 获取原始字节。
    """
    if driver is None:
        return None
    current_handle = driver.current_window_handle
    data_bytes = None
    try:
        driver.execute_script("window.open('about:blank','_blank');")
        new_handle = [h for h in driver.window_handles if h != current_handle][-1]
        driver.switch_to.window(new_handle)
        driver.get(url)
        time.sleep(0.5)
        script = r"""
        const callback = arguments[arguments.length - 1];
        const tryFetch = async () => {
          // Preferred: Tampermonkey API
          if (typeof window.__GET_IMAGE_BASE64__ === 'function') {
            try {
              const res = await window.__GET_IMAGE_BASE64__();
              if (res && res.ok) return res;
            } catch (e) {
              // fall through
            }
          }

          // Fallback: canvas -> dataURL
          try {
            const img = document.querySelector('img');
            if (img && img.naturalWidth && img.naturalHeight) {
              const canvas = document.createElement('canvas');
              canvas.width = img.naturalWidth;
              canvas.height = img.naturalHeight;
              const ctx = canvas.getContext('2d');
              ctx.drawImage(img, 0, 0);
              const dataUrl = canvas.toDataURL('image/png');
              return { ok: true, base64: dataUrl.split(',')[1], mime: 'image/png' };
            }
          } catch (e) {
            // fall through
          }

          // Final fallback: fetch the URL with credentials
          try {
            const resp = await fetch(window.location.href, { credentials: 'include' });
            const buf = await resp.arrayBuffer();
            const bytes = new Uint8Array(buf);
            let binary = '';
            const chunk = 8192;
            for (let i = 0; i < bytes.length; i += chunk) {
              const sub = bytes.subarray(i, i + chunk);
              binary += String.fromCharCode.apply(null, sub);
            }
            const base64 = btoa(binary);
            const mime = resp.headers.get('content-type') || 'image/jpeg';
            return { ok: true, base64, mime };
          } catch (err) {
            return { ok: false, error: String(err) };
          }
        };
        tryFetch().then(res => callback(res)).catch(err => callback({ ok: false, error: String(err) }));
        """
        result = driver.execute_async_script(script)
        if isinstance(result, dict) and result.get("ok") and result.get("base64"):
            data_bytes = base64.b64decode(result["base64"])
        else:
            print(f"DOM fetch new tab failed for {url}: {result}")
    except Exception as exc:
        print(f"New tab DOM fetch failed for {url}: {exc}")
    finally:
        try:
            driver.close()
        except Exception:
            pass
        try:
            driver.switch_to.window(current_handle)
        except Exception:
            pass
    return data_bytes


def _fetch_image_bytes(url: str, driver=None, referer: Optional[str] = None) -> Optional[bytes]:
    """Fetch image bytes using the real browser context; prefer TM API via new tab first."""
    # Prefer Tampermonkey bridge (new tab) so anti-hotlink is less likely to trigger.
    content = _dom_fetch_image_new_tab(driver, url)
    if content is None:
        content = _browser_fetch_image(driver, url)
    return content


def _download_image(url: str, dest_dir: str, filename_prefix: str, index: int, driver=None,
                   referer: Optional[str] = None) -> Optional[str]:
    """Download image to destination directory, return local path on success."""
    if not url:
        return None
    os.makedirs(dest_dir, exist_ok=True)

    parsed = urlparse(url)
    ext = os.path.splitext(parsed.path)[1]
    if not ext or len(ext) > 5:
        ext = ".jpg"
    base_name = os.path.basename(parsed.path) or "img"
    safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", base_name)
    short_hash = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
    filename = f"{filename_prefix}_{index}_{short_hash}{ext}"
    local_path = os.path.join(dest_dir, filename)

    content = _fetch_image_bytes(url, driver=driver, referer=referer)

    if content is None:
        try:
            if os.path.exists(local_path):
                os.remove(local_path)
        except OSError:
            pass
        return None

    try:
        with open(local_path, "wb") as f:
            f.write(content)
        return local_path
    except Exception as exc:
        print(f"Failed to save image {url}: {exc}")
        try:
            if os.path.exists(local_path):
                os.remove(local_path)
        except OSError:
            pass
        return None


def _save_product_data_to_files(product_data: ProductData, original_dict: Dict[str, Any],
                               output_folder: Optional[str] = None, driver=None):
    """Save product data to files."""
    if output_folder is None:
        # Create timestamped folder
        main_output_folder = "scraped_data"
        os.makedirs(main_output_folder, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_folder = os.path.join(main_output_folder, f"scraped_data_{timestamp}")
        os.makedirs(output_folder, exist_ok=True)

    print(f"Saving data to folder: {output_folder}")

    images_root = os.path.join(output_folder, "images")
    main_image_dir = os.path.join(images_root, "main")
    detail_image_dir = os.path.join(images_root, "detail")
    os.makedirs(main_image_dir, exist_ok=True)
    os.makedirs(detail_image_dir, exist_ok=True)

    # Download images: main (style images) and detail images
    manifest = {"main": [], "detail": []}

    # Main images (styles)
    seen_main = set()
    referer = product_data.product_info.url

    for idx, style in enumerate(product_data.styles, start=1):
        img_url = style.image_url
        if not img_url or img_url in seen_main:
            continue
        seen_main.add(img_url)
        local_path = _download_image(img_url, main_image_dir, "main", idx, driver=driver, referer=referer)
        if local_path:
            manifest["main"].append({
                "url": img_url,
                "file": os.path.relpath(local_path, output_folder),
                "original_filename": os.path.basename(urlparse(img_url).path)
            })

    # Detail images (图文详情)
    seen_detail = set()
    for idx, img_url in enumerate(product_data.product_details.image_details, start=1):
        if not img_url or img_url in seen_detail:
            continue
        seen_detail.add(img_url)
        local_path = _download_image(img_url, detail_image_dir, "detail", idx, driver=driver, referer=referer)
        if local_path:
            manifest["detail"].append({
                "url": img_url,
                "file": os.path.relpath(local_path, output_folder),
                "original_filename": os.path.basename(urlparse(img_url).path)
            })

    manifest_path = os.path.join(images_root, "download_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"Image manifest saved to {manifest_path}")

    # Run OCR using downloaded local files (avoid re-fetching)
    ocr_file_cache: Dict[str, Any] = {}

    # Styles main images OCR
    main_map = {entry["url"]: entry["file"] for entry in manifest["main"]}
    main_texts: List[str] = []
    for style in product_data.styles:
        img_url = style.image_url
        if img_url in main_map:
            local_rel = main_map[img_url]
            local_path = os.path.join(output_folder, local_rel)
            ocr_dict = _run_ocr_from_file(local_path, cache=ocr_file_cache)
            if ocr_dict:
                style.ocr = _dict_to_ocr_result(ocr_dict)
                if style.ocr.full_text:
                    main_texts.append(style.ocr.full_text)

    # Detail images OCR
    detail_map = {entry["url"]: entry["file"] for entry in manifest["detail"]}
    detail_ocr_results: List[OCRResult] = []
    for url in product_data.product_details.image_details:
        if url in detail_map:
            local_rel = detail_map[url]
            local_path = os.path.join(output_folder, local_rel)
            ocr_dict = _run_ocr_from_file(local_path, cache=ocr_file_cache)
            if ocr_dict:
                detail_ocr_results.append(_dict_to_ocr_result(ocr_dict))
    if detail_ocr_results:
        product_data.product_details.image_details_ocr = detail_ocr_results
        texts = [r.full_text for r in detail_ocr_results if r.full_text]
        product_data.product_details.detail_images_ocr_text = "\n".join(texts)
    if main_texts:
        # Deduplicate
        seen = set()
        unique_texts = []
        for t in main_texts:
            if t not in seen:
                seen.add(t)
                unique_texts.append(t)
        product_data.product_details.main_images_ocr_text = "\n".join(unique_texts)

    # Save as JSON (convert dataclass to dict) and replace image URLs with local paths
    json_data = asdict(product_data)

    main_map = {entry["url"]: entry["file"] for entry in manifest["main"]}
    detail_map = {entry["url"]: entry["file"] for entry in manifest["detail"]}

    for style in json_data.get("styles", []):
        url = style.get("image_url")
        if url and url in main_map:
            style["image_url_original"] = url
            style["image_url"] = main_map[url]

    details_dict = json_data.get("product_details", {})
    if "image_details" in details_dict:
        original_list = list(details_dict.get("image_details", []))
        details_dict["image_details_original"] = original_list
        replaced = []
        for url in original_list:
            if url in detail_map:
                replaced.append(detail_map[url])
            else:
                replaced.append(url)
        details_dict["image_details"] = replaced
        json_data["product_details"] = details_dict

    filename = os.path.join(output_folder, "product_data.json")
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)
    print(f"Data saved to {filename}")

    # Save readable version
    readable_filename = os.path.join(output_folder, "product_data_readable.txt")
    with open(readable_filename, 'w', encoding='utf-8') as f:
        f.write("Product Information\n")
        f.write("=" * 50 + "\n\n")

        # Product info
        f.write(f"Title: {product_data.product_info.title}\n")
        f.write(f"URL: {product_data.product_info.url}\n")

        # Shop info
        f.write("\nShop Information:\n")
        f.write(f"  Name: {product_data.product_info.shop.name}\n")
        f.write(f"  Rating: {product_data.product_info.shop.rating}\n")
        f.write(f"  Good Review Rate: {product_data.product_info.shop.good_review_rate}\n")

        # Styles
        f.write("\nStyle Variations:\n")
        for idx, style in enumerate(product_data.styles, 1):
            f.write(f"\nStyle {idx}: {style.style_name}\n")
            f.write(f"  Status: {'有货' if style.available else '缺货'}\n")
            f.write(f"  Sizes: {', '.join([s.name for s in style.sizes])}\n")

        # Reviews count
        f.write(f"\nTotal Reviews: {len(product_data.product_details.reviews)}\n")
        f.write(f"Total Parameters: {len(product_data.product_details.parameters)}\n")

    print(f"Readable version saved to {readable_filename}")

    # Save raw HTML files if they exist
    params_raw = original_dict.get('product_details', {}).get('parameters_raw', '')
    if params_raw:
        params_filename = os.path.join(output_folder, "parameters_raw.html")
        with open(params_filename, 'w', encoding='utf-8') as f:
            f.write(params_raw)
        print(f"Raw parameters HTML saved to {params_filename}")

    img_raw = original_dict.get('product_details', {}).get('image_details_raw', '')
    if img_raw:
        img_filename = os.path.join(output_folder, "image_details_raw.html")
        with open(img_filename, 'w', encoding='utf-8') as f:
            f.write(img_raw)
        print(f"Raw image details HTML saved to {img_filename}")


def main():
    """Main execution function."""
    # Check if URL is provided as command line argument
    if len(sys.argv) > 1:
        product_url = sys.argv[1]
        print(f"Using URL from command line: {product_url}")
    else:
        # Default URL if no command line argument is provided
        # --- IMPORTANT ---
        # The default URL to be scraped.
        # This is the example URL the user wants to analyze.
        product_url = "https://item.taobao.com/item.htm?id=853761881909&mi_id=0000CNMiLjV6zCXIf4sIAtDPnmJn0j3GxDUQGpTXwZioNwo&pvid=3ec3f4c5-2b45-47f8-adea-18098ff14f58&scm=1007.40986.467924.0&skuId=5820967066670&spm=a21bo.jianhua%2Fa.201876.d4.5af92a89ByDof5&utparam=%7B%22item_ctr%22%3A0.10585758090019226%2C%22x_object_type%22%3A%22item%22%2C%22matchType%22%3A%22nann_base%22%2C%22item_price%22%3A%22199%22%2C%22item_cvr%22%3A0.006797492504119873%2C%22umpCalled%22%3Atrue%2C%22pc_ctr%22%3A0.11560603976249695%2C%22pc_scene%22%3A%2220001%22%2C%22userId%22%3A2870588993%2C%22ab_info%22%3A%2230986%23467924%230_30986%23528214%2358507_30986%23527807%2358418_30986%23528109%2358485_30986%23521582%2357267_30986%23526064%2358189_30986%23528938%2357910_30986%23533296%2359487_30986%23530923%2359037_30986%23532805%2359017%22%2C%22tpp_buckets%22%3A%2230986%23467924%230_30986%23528214%2358507_30986%23527807%2358418_30986%23528109%2358485_30986%23521582%2357267_30986%23526064%2358189_30986%23528938%2357910_30986%23533296%2359487_30986%23530923%2359037_30986%23532805%2359017%22%2C%22aplus_abtest%22%3A%221f612159075e23338e1f22d6afa4cb23%22%2C%22isLogin%22%3Atrue%2C%22abid%22%3A%22528214_527807_528109_521582_526064_528938_533296_530923_532805%22%2C%22pc_pvid%22%3A%223ec3f4c5-2b45-47f8-adea-18098ff14f58%22%2C%22isWeekLogin%22%3Afalse%2C%22pc_alg_score%22%3A0.3136315665129%2C%22rn%22%3A3%2C%22item_ecpm%22%3A0%2C%22ump_price%22%3A%22199%22%2C%22isXClose%22%3Afalse%2C%22x_object_id%22%3A853761881909%7D&xxc=home_recommend"

    # Create main output folder if it doesn't exist
    main_output_folder = "scraped_data"
    os.makedirs(main_output_folder, exist_ok=True)

    # Create subfolder with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_folder = os.path.join(main_output_folder, f"scraped_data_{timestamp}")
    os.makedirs(output_folder, exist_ok=True)
    print(f"Output will be saved to folder: {output_folder}")

    # Use the new entry point function
    product_data = scrape_product_data(
        product_url=product_url,
        save_to_file=True,
        output_folder=output_folder
    )

    if product_data:
        print("\n--- Scraping Complete ---")
        # Print summary to console
        print("\nScraping Summary:")
        print(f"- Found {len(product_data.styles)} style variations")
        print(f"- Found {len(product_data.product_details.reviews)} reviews")
        print(f"- Found {len(product_data.product_details.parameters)} parameters")

        # Check if raw DOM data was saved
        if product_data.product_details.parameters_raw:
            print(f"- Raw parameters DOM: {len(product_data.product_details.parameters_raw)} characters")
        if product_data.product_details.image_details_raw:
            print(f"- Raw image details DOM: {len(product_data.product_details.image_details_raw)} characters")
    else:
        print("\n--- Scraping Failed ---")
        print("Could not retrieve product style information.")

if __name__ == "__main__":
    main()
