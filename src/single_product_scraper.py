
import json
import time
import os
import sys
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, NoSuchElementException

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
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    return driver

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
                    label_span = item.find_element(By.XPATH, './/span[@title="颜色分类" or contains(text(), "颜色")]')
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
                # Find all valueItem elements (this will find nested ones too, but we'll filter)
                all_value_items = content_div.find_elements(By.CSS_SELECTOR, '[class*="valueItem"]')

                # Filter to only get top-level valueItem elements (those with hasImg class)
                style_elements = []
                for item in all_value_items:
                    class_attr = item.get_attribute('class') or ''
                    # Only include items that have hasImg class (these are the color options)
                    if 'hasImg' in class_attr and 'valueItem' in class_attr:
                        style_elements.append(item)

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

            print(f"\nProcessing Style {index + 1}: {style_data['style_name']}")

            # 2. Click the style to trigger updates
            try:
                # Get the current main image URL to detect changes later
                initial_img_src = driver.find_element(By.ID, "mainPicImageEl").get_attribute('src')
                driver.execute_script("arguments[0].click();", style_element)
            except Exception as e:
                print(f"  - Could not click on style '{style_data['style_name']}'. Error: {e}")
                continue

            # 3. Wait for the main image to update and get the new URL
            try:
                # Wait a moment for the image to load
                time.sleep(0.5)
                # Get the main image element - it has id="mainPicImageEl"
                main_img = driver.find_element(By.ID, "mainPicImageEl")
                current_img_src = main_img.get_attribute('src')

                if current_img_src != initial_img_src:
                    style_data["image_url"] = current_img_src
                    print("  - Image updated successfully.")
                else:
                    # If we already got the image from the thumbnail, use that
                    if style_data.get("image_url") == "N/A":
                        style_data["image_url"] = current_img_src
                    print("  - Using current image URL.")
            except Exception as e:
                print(f"  - Error getting main image: {e}")
                # Use the initial image as fallback
                if style_data.get("image_url") == "N/A":
                    style_data["image_url"] = initial_img_src


            # 4. Get available sizes for the current style - read after selecting style
            available_sizes = []
            try:
                # After clicking a style, we need to find the size SKU section
                size_sku_item = None
                sku_items = sku_container.find_elements(By.CSS_SELECTOR, '[class*="skuItem"]')

                for item in sku_items:
                    try:
                        # Look for the item containing "尺码" text
                        size_span = item.find_element(By.XPATH, './/span[@title="尺码" or contains(text(), "尺码")]')
                        if size_span:
                            size_sku_item = item
                            break
                    except NoSuchElementException:
                        continue

                if size_sku_item:
                    # Find the size options in the size section
                    sku_value_wrap = size_sku_item.find_element(By.CSS_SELECTOR, '[class*="skuValueWrap"]')
                    content_div = sku_value_wrap.find_element(By.CSS_SELECTOR, '[class*="content"]')
                    # Find all valueItem elements within the content div
                    size_elements = content_div.find_elements(By.CSS_SELECTOR, '[class*="valueItem"]')
                    print(f"  - Debug: Found {len(size_elements)} size elements")

                    # Filter out disabled sizes
                    for size_element in size_elements:
                        # Check if the size is disabled using data-disabled attribute
                        data_disabled = size_element.get_attribute('data-disabled')
                        if data_disabled == 'true':
                            continue

                        # Also check class for disabled indicators
                        class_attr = size_element.get_attribute('class') or ''
                        if 'disabled' in class_attr.lower():
                            continue

                        # Get the size name from the valueItemText span
                        try:
                            size_name_tag = size_element.find_element(By.CSS_SELECTOR, 'span[class*="valueItemText"]')
                            size_name = size_name_tag.get_attribute('title') or size_name_tag.text.strip()
                            if size_name and size_name not in available_sizes:
                                available_sizes.append(size_name)
                                print(f"    - Added size: {size_name}")
                        except Exception as e:
                            # Fallback to direct text
                            size_name = size_element.text.strip()
                            if size_name and size_name not in available_sizes:
                                available_sizes.append(size_name)
                                print(f"    - Added size (fallback): {size_name}")

                    style_data["available_sizes"] = available_sizes
                    print(f"  - Found sizes: {available_sizes}")
                else:
                    print("  - Could not find size SKU section")

            except Exception as e:
                print(f"  - Error getting sizes: {e}")

            all_styles_data.append(style_data)
            time.sleep(0.5) # Small delay between clicks

    except (TimeoutException, NoSuchElementException) as e:
        print(f"Error finding essential SKU components on the page. Please check the URL. Error: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None

    # Extract product title and shop info
    product_title = ""
    shop_info = {}

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

    # Prepare final result with all data
    result = {
        "product_info": {
            "title": product_title,
            "url": product_url,
            "shop": shop_info
        },
        "styles": all_styles_data,
        "product_details": scrape_product_details(driver)
    }

    return result

def scrape_product_details(driver):
    """Scrape product details including reviews, parameters and image details"""
    details = {
        "reviews": [],
        "parameters": {},
        "parameters_raw": "",  # Store raw DOM for parameters
        "image_details": [],
        "image_details_raw": ""  # Store raw DOM for image details
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
                        param_name = title_elem.get_attribute('title') or title_elem.text.strip()
                        param_value = subtitle_elem.get_attribute('title') or subtitle_elem.text.strip()
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

    driver = setup_driver()

    try:
        print("Opening Taobao/Tmall. Please log in manually if required within 5 seconds.")
        driver.get("https://www.taobao.com")
        time.sleep(5)
        print("Login period over. Starting scrape...")

        product_info = scrape_single_product(driver, product_url)

        if product_info:
            print("\n--- Scraping Complete ---")

            # Always save to a file with timestamp
            filename = os.path.join(output_folder, "product_data.json")
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(product_info, f, indent=2, ensure_ascii=False)
            print(f"\nData saved to {filename}")

            # Also save a more readable version
            readable_filename = os.path.join(output_folder, "product_data_readable.txt")
            with open(readable_filename, 'w', encoding='utf-8') as f:
                f.write("Product Information\n")
                f.write("=" * 50 + "\n\n")

                # Write product basic info
                f.write("PRODUCT BASIC INFO:\n")
                f.write("-" * 30 + "\n")
                product_basic_info = product_info.get('product_info', {})
                f.write(f"Title: {product_basic_info.get('title', 'N/A')}\n")
                f.write(f"URL: {product_basic_info.get('url', 'N/A')}\n")

                shop_info = product_basic_info.get('shop', {})
                f.write(f"\nShop Information:\n")
                f.write(f"  Name: {shop_info.get('name', 'N/A')}\n")
                f.write(f"  URL: {shop_info.get('url', 'N/A')}\n")
                f.write(f"  Rating: {shop_info.get('rating', 'N/A')}\n")
                f.write(f"  Good Review Rate: {shop_info.get('good_review_rate', 'N/A')}\n")
                f.write("\n")

                # Write styles
                f.write("STYLE VARIATIONS:\n")
                f.write("-" * 30 + "\n")
                for idx, style in enumerate(product_info.get('styles', []), 1):
                    f.write(f"Style {idx}: {style['style_name']}\n")
                    f.write(f"  Image URL: {style['image_url']}\n")
                    f.write(f"  Available Sizes: {', '.join(style['available_sizes']) if style['available_sizes'] else 'N/A'}\n")
                    f.write("\n")

                # Get product details from correct structure
                product_details = product_info.get('product_details', {})

                # Write reviews
                f.write("\nUSER REVIEWS:\n")
                f.write("-" * 30 + "\n")
                reviews = product_details.get('reviews', [])
                if reviews:
                    for idx, review in enumerate(reviews[:5], 1):
                        f.write(f"Review {idx}:\n")
                        f.write(f"  User: {review['user']}\n")
                        f.write(f"  Date/Purchase: {review['meta']}\n")
                        f.write(f"  Content: {review['content'][:200]}...\n")
                        if review.get('images'):
                            f.write(f"  Images: {len(review['images'])} images\n")
                        f.write("\n")
                else:
                    f.write("No reviews found.\n\n")

                # Write parameters
                f.write("PRODUCT PARAMETERS:\n")
                f.write("-" * 30 + "\n")
                params = product_details.get('parameters', {})
                if params:
                    for key, value in params.items():
                        f.write(f"{key}: {value}\n")
                else:
                    f.write("No parameters found.\n")

                # Save raw HTML for parameters in separate file
                params_raw = product_details.get('parameters_raw', '')
                if params_raw:
                    params_html_filename = os.path.join(output_folder, "parameters_raw.html")
                    with open(params_html_filename, 'w', encoding='utf-8') as params_file:
                        params_file.write(params_raw)
                    f.write(f"\n[Raw parameters HTML saved to: parameters_raw.html]\n")

                # Save raw HTML for image details in separate file
                f.write("\n\nIMAGE DETAILS:\n")
                f.write("-" * 30 + "\n")
                image_details = product_details.get('image_details', [])
                if image_details:
                    f.write(f"Found {len(image_details)} images:\n")
                    for idx, img_url in enumerate(image_details, 1):
                        f.write(f"  {idx}. {img_url}\n")
                else:
                    f.write("No images found.\n")

                # Save raw HTML for image details
                img_details_raw = product_details.get('image_details_raw', '')
                if img_details_raw:
                    img_html_filename = os.path.join(output_folder, "image_details_raw.html")
                    with open(img_html_filename, 'w', encoding='utf-8') as img_file:
                        img_file.write(img_details_raw)
                    f.write(f"\n[Raw image details HTML saved to: image_details_raw.html]\n")

            print(f"Readable version saved to {readable_filename}")

            # Save debug HTML files if they exist
            debug_files = ["debug_page_source.html", "debug_sku_container.html"]
            for debug_file in debug_files:
                if os.path.exists(debug_file):
                    dest = os.path.join(output_folder, debug_file)
                    os.rename(debug_file, dest)
                    print(f"Debug file {debug_file} moved to {dest}")

            # Print summary to console
            print("\nScraping Summary:")
            print(f"- Found {len(product_info.get('styles', []))} style variations")
            print(f"- Found {len(product_info.get('product_details', {}).get('reviews', []))} reviews")
            print(f"- Found {len(product_info.get('product_details', {}).get('parameters', {}))} parameters")

            # Check if raw DOM data was saved
            product_details = product_info.get('product_details', {})
            if product_details.get('parameters_raw'):
                print(f"- Raw parameters DOM: {len(product_details['parameters_raw'])} characters")
            if product_details.get('image_details_raw'):
                print(f"- Raw image details DOM: {len(product_details['image_details_raw'])} characters")

            print(f"\nAll files saved in folder: {output_folder}")

        else:
            print("\n--- Scraping Failed ---")
            print("Could not retrieve product style information.")

    finally:
        print("\nClosing browser.")
        driver.quit()

if __name__ == "__main__":
    main()
