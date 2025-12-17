import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

def scrape_product_detail_page(driver, product_url):
    """
    Comprehensive product scraping that extracts all style variations, sizes, and product details
    Based on single_product_scraper.py implementation
    """
    print(f"Scraping product: {product_url}")
    driver.get(product_url)
    time.sleep(3)

    # Scroll down to load the detail section
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(2)

    product_data = {
        "name": "N/A",
        "price": "N/A",
        "styles": "N/A",
        "stock": "N/A",
        "image_url": "N/A",
        "url": product_url,
        "shop_name": "N/A",
        "shop_url": "N/A",
        "shop_rating": "N/A",
        "reviews_count": "N/A",
        "parameters": "N/A"
    }

    try:
        # Extract basic product info
        product_data.update(extract_basic_product_info(driver))

        # Extract style and size variations
        styles_info = extract_style_and_size_variations(driver)
        if styles_info:
            product_data["styles"] = f"{len(styles_info)} styles"
            available_styles = [s for s in styles_info if s.get("available", True)]
            product_data["stock"] = f"{len(available_styles)}/{len(styles_info)} styles available"

        # Extract shop information
        shop_info = extract_shop_info(driver)
        product_data.update(shop_info)

        # Extract product details (reviews, parameters)
        details = extract_product_details_summary(driver)
        product_data.update(details)

    except Exception as e:
        print(f"  - Error scraping product: {e}")

    return product_data

def extract_basic_product_info(driver):
    """Extract basic product information"""
    info = {
        "name": "N/A",
        "price": "N/A",
        "image_url": "N/A"
    }

    try:
        # Extract product title
        title_element = driver.find_element(By.CSS_SELECTOR, '[class*="mainTitle--"]')
        info["name"] = title_element.get_attribute('title') or title_element.text.strip()
    except Exception:
        try:
            # Fallback selectors
            title_element = driver.find_element(By.CSS_SELECTOR, 'div[class*="MainTitle"]')
            info["name"] = title_element.text.strip()
        except Exception:
            pass

    try:
        # Extract price
        price_element = driver.find_element(By.CSS_SELECTOR, 'div[class*="highlightPrice"] span[class*="text"]')
        info["price"] = price_element.text.strip()
    except Exception:
        try:
            # Fallback price selector
            price_element = driver.find_element(By.CSS_SELECTOR, '[class*="price--"]')
            info["price"] = price_element.text.strip()
        except Exception:
            pass

    try:
        # Extract main image
        image_element = driver.find_element(By.ID, "mainPicImageEl")
        info["image_url"] = image_element.get_attribute('src')
    except Exception:
        try:
            # Fallback image selector
            image_element = driver.find_element(By.ID, "J_ImgBooth")
            info["image_url"] = image_element.get_attribute('src')
        except Exception:
            pass

    return info

def extract_style_and_size_variations(driver):
    """Extract style variations and sizes"""
    all_styles = []

    try:
        # Wait for the SKU component
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
                break
            except TimeoutException:
                continue

        if not sku_container:
            return all_styles

        # Find style/color options
        style_elements = []
        try:
            # Find color SKU item
            color_sku_item = None
            sku_items = sku_container.find_elements(By.CSS_SELECTOR, '[class*="skuItem"]')

            for item in sku_items:
                try:
                    label_span = item.find_element(By.XPATH, './/span[@title="颜色分类" or contains(text(), "颜色")]')
                    if label_span:
                        color_sku_item = item
                        break
                except NoSuchElementException:
                    continue

            if color_sku_item:
                sku_value_wrap = color_sku_item.find_element(By.CSS_SELECTOR, '[class*="skuValueWrap"]')
                content_div = sku_value_wrap.find_element(By.CSS_SELECTOR, '[class*="content"]')
                all_value_items = content_div.find_elements(By.CSS_SELECTOR, '[class*="valueItem"]')

                for item in all_value_items:
                    class_attr = item.get_attribute('class') or ''
                    if 'hasImg' in class_attr and 'valueItem' in class_attr:
                        style_elements.append(item)
        except Exception:
            pass

        # Extract style information
        for index, style_element in enumerate(style_elements):
            style_data = {
                "style_name": f"Style_{index + 1}",
                "available": False,
                "sizes": []
            }

            # Check availability
            data_disabled = style_element.get_attribute('data-disabled') or 'false'
            style_data["available"] = data_disabled == 'false'

            # Get style name
            try:
                style_name_tag = style_element.find_element(By.CSS_SELECTOR, 'span[class*="valueItemText"]')
                style_name = style_name_tag.get_attribute('title') or style_name_tag.text.strip()
                if style_name:
                    style_data["style_name"] = style_name
            except Exception:
                pass

            # Get image
            try:
                img_tag = style_element.find_element(By.CSS_SELECTOR, 'img[class*="valueItemImg"]')
                style_data["image_url"] = img_tag.get_attribute('src')
            except Exception:
                pass

            # Get sizes
            try:
                size_sku_item = None
                sku_items = sku_container.find_elements(By.CSS_SELECTOR, '[class*="skuItem"]')

                for item in sku_items:
                    try:
                        size_span = item.find_element(By.XPATH, './/span[@title="尺码" or contains(text(), "尺码")]')
                        if size_span:
                            size_sku_item = item
                            break
                    except NoSuchElementException:
                        continue

                if size_sku_item:
                    sku_value_wrap = size_sku_item.find_element(By.CSS_SELECTOR, '[class*="skuValueWrap"]')
                    content_div = sku_value_wrap.find_element(By.CSS_SELECTOR, '[class*="content"]')
                    size_elements = content_div.find_elements(By.CSS_SELECTOR, '[class*="valueItem"]')

                    for size_element in size_elements:
                        try:
                            size_name_tag = size_element.find_element(By.CSS_SELECTOR, 'span[class*="valueItemText"]')
                            size_name = size_name_tag.get_attribute('title') or size_name_tag.text.strip()
                        except Exception:
                            size_name = size_element.text.strip()

                        if size_name:
                            size_data_disabled = size_element.get_attribute('data-disabled') or 'false'
                            size_is_available = size_data_disabled == 'false'

                            style_data["sizes"].append({
                                "name": size_name,
                                "available": size_is_available
                            })
            except Exception:
                pass

            all_styles.append(style_data)

    except Exception as e:
        print(f"  - Error extracting styles: {e}")

    return all_styles

def extract_shop_info(driver):
    """Extract shop information"""
    shop_info = {
        "shop_name": "N/A",
        "shop_url": "N/A",
        "shop_rating": "N/A"
    }

    try:
        shop_header = driver.find_element(By.CSS_SELECTOR, '[class*="shopHeader--"]')

        # Shop name
        try:
            shop_name_elem = shop_header.find_element(By.CSS_SELECTOR, '[class*="shopName--"]')
            shop_info["shop_name"] = shop_name_elem.get_attribute('title') or shop_name_elem.text.strip()
        except:
            pass

        # Shop URL
        try:
            shop_link = shop_header.find_element(By.CSS_SELECTOR, 'a[href*="shop"]')
            shop_url = shop_link.get_attribute('href')
            if shop_url and shop_url.startswith('//'):
                shop_url = 'https:' + shop_url
            shop_info["shop_url"] = shop_url
        except:
            pass

        # Shop rating
        try:
            rating_elem = shop_header.find_element(By.CSS_SELECTOR, '[class*="starNum--"]')
            shop_info["shop_rating"] = rating_elem.text.strip()
        except:
            pass

    except Exception as e:
        print(f"  - Error extracting shop info: {e}")

    return shop_info

def extract_product_details_summary(driver):
    """Extract a summary of product details (reviews, parameters)"""
    details = {
        "reviews_count": "N/A",
        "parameters": "N/A"
    }

    try:
        # Try to find review count
        try:
            review_elements = driver.find_elements(By.CSS_SELECTOR, '[class*="Comment--"]')
            if review_elements:
                details["reviews_count"] = str(len(review_elements))
        except:
            pass

        # Try to extract key parameters
        try:
            params_area = driver.find_element(By.CSS_SELECTOR, '[class*="paramsInfoArea"]')
            param_elements = params_area.find_elements(By.CSS_SELECTOR, '[class*="emphasisParamsInfoItem--"], [class*="generalParamsInfoItem--"]')

            if param_elements:
                param_summary = []
                for param_elem in param_elements[:5]:  # Limit to first 5 parameters
                    try:
                        title_elem = param_elem.find_element(By.CSS_SELECTOR, '[class*="ItemTitle--"], [class*="InfoItemTitle--"]')
                        subtitle_elem = param_elem.find_element(By.CSS_SELECTOR, '[class*="ItemSubTitle--"], [class*="InfoItemSubTitle--"]')

                        param_name = title_elem.get_attribute('title') or title_elem.text.strip()
                        param_value = subtitle_elem.get_attribute('title') or subtitle_elem.text.strip()

                        if param_name and param_value:
                            param_summary.append(f"{param_name}: {param_value}")
                    except:
                        continue

                if param_summary:
                    details["parameters"] = "; ".join(param_summary)
        except:
            pass

    except Exception as e:
        print(f"  - Error extracting product details: {e}")

    return details