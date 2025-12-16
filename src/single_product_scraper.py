
import json
import time
import os
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
    """
    print(f"Navigating to product page: {product_url}")
    driver.get(product_url)

    # Wait a bit for page to fully load
    time.sleep(3)

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

    return all_styles_data

def main():
    """Main execution function."""
    # --- IMPORTANT ---
    # The URL to be scraped should be provided here.
    # This is the example URL the user wants to analyze.
    product_url = "https://item.taobao.com/item.htm?id=853761881909&mi_id=0000CNMiLjV6zCXIf4sIAtDPnmJn0j3GxDUQGpTXwZioNwo&pvid=3ec3f4c5-2b45-47f8-adea-18098ff14f58&scm=1007.40986.467924.0&skuId=5820967066670&spm=a21bo.jianhua%2Fa.201876.d4.5af92a89ByDof5&utparam=%7B%22item_ctr%22%3A0.10585758090019226%2C%22x_object_type%22%3A%22item%22%2C%22matchType%22%3A%22nann_base%22%2C%22item_price%22%3A%22199%22%2C%22item_cvr%22%3A0.006797492504119873%2C%22umpCalled%22%3Atrue%2C%22pc_ctr%22%3A0.11560603976249695%2C%22pc_scene%22%3A%2220001%22%2C%22userId%22%3A2870588993%2C%22ab_info%22%3A%2230986%23467924%230_30986%23528214%2358507_30986%23527807%2358418_30986%23528109%2358485_30986%23521582%2357267_30986%23526064%2358189_30986%23528938%2357910_30986%23533296%2359487_30986%23530923%2359037_30986%23532805%2359017%22%2C%22tpp_buckets%22%3A%2230986%23467924%230_30986%23528214%2358507_30986%23527807%2358418_30986%23528109%2358485_30986%23521582%2357267_30986%23526064%2358189_30986%23528938%2357910_30986%23533296%2359487_30986%23530923%2359037_30986%23532805%2359017%22%2C%22aplus_abtest%22%3A%221f612159075e23338e1f22d6afa4cb23%22%2C%22isLogin%22%3Atrue%2C%22abid%22%3A%22528214_527807_528109_521582_526064_528938_533296_530923_532805%22%2C%22pc_pvid%22%3A%223ec3f4c5-2b45-47f8-adea-18098ff14f58%22%2C%22isWeekLogin%22%3Afalse%2C%22pc_alg_score%22%3A0.3136315665129%2C%22rn%22%3A3%2C%22item_ecpm%22%3A0%2C%22ump_price%22%3A%22199%22%2C%22isXClose%22%3Afalse%2C%22x_object_id%22%3A853761881909%7D&xxc=home_recommend" # Replace with the actual URL if needed

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
            filename = f"product_styles_{int(time.time())}.json"
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(product_info, f, indent=2, ensure_ascii=False)
            print(f"\nData saved to {filename}")

            # Also save a more readable version
            readable_filename = f"product_styles_readable_{int(time.time())}.txt"
            with open(readable_filename, 'w', encoding='utf-8') as f:
                f.write("Product Style Information\n")
                f.write("=" * 50 + "\n\n")

                for idx, style in enumerate(product_info, 1):
                    f.write(f"Style {idx}: {style['style_name']}\n")
                    f.write(f"  Image URL: {style['image_url']}\n")
                    f.write(f"  Available Sizes: {', '.join(style['available_sizes']) if style['available_sizes'] else 'N/A'}\n")
                    f.write("-" * 30 + "\n")

            print(f"Readable version saved to {readable_filename}")

            # Also print the result to console
            print("\nScraped Data:")
            print(json.dumps(product_info, indent=2, ensure_ascii=False))

        else:
            print("\n--- Scraping Failed ---")
            print("Could not retrieve product style information.")

    finally:
        print("\nClosing browser.")
        driver.quit()

if __name__ == "__main__":
    main()
