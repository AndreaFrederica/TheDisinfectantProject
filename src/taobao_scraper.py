import json5
import time
import re
import os
from typing import Optional, List
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.driver_cache import DriverCacheManager
from single_product_scraper import scrape_product_data, ProductData, asdict

# --- Configuration and Setup ---

def load_shops_from_config(file_path="src/shops.json5"):
    """从json5文件加载店铺列表"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json5.load(f)
    except FileNotFoundError:
        print(f"错误：找不到配置文件 {file_path}")
        return []
    except Exception as e:
        print(f"解析配置文件时出错: {e}")
        return []

def setup_driver():
    """初始化并返回一个Chrome WebDriver实例，并开启日志记录"""
    options = webdriver.ChromeOptions()
    profile_path = os.path.abspath('chrome_profile')
    options.add_argument(f'user-data-dir={profile_path}')
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument('--ignore-certificate-errors')
    os.makedirs(profile_path, exist_ok=True)

    # 开启浏览器日志记录
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
    
    driver_cache_dir = os.path.abspath(os.path.join(profile_path, "driver_cache"))
    os.makedirs(driver_cache_dir, exist_ok=True)
    cache_manager = DriverCacheManager(root_dir=driver_cache_dir, valid_range=30)
    service = Service(ChromeDriverManager(cache_manager=cache_manager).install())
    driver = webdriver.Chrome(service=service, options=options)
    return driver

# --- Scraping Core Functions ---

def get_all_product_links_via_click_intercept(driver, shop_url):
    """
    通过注入JS拦截window.open并模拟点击的方式，获取所有商品链接
    """
    print(f"访问店铺页面: {shop_url}")
    driver.get(shop_url)
    time.sleep(3)

    # 注入JS拦截脚本
    js_interceptor = """
    (function () {
      window._captured_urls = window._captured_urls || [];
      const _open = window.open;
      window.open = function (url, ...rest) {
        console.log('[拦截并抓取]', url);
        window._captured_urls.push(url);
        return null; // 阻止打开新窗口
      };
      console.log('已安装链接拦截器');
    })();
    """
    driver.execute_script(js_interceptor)
    print("已成功向页面注入JS链接拦截器。")

    print("开始向下滚动并模拟点击...")
    last_height = driver.execute_script("return document.body.scrollHeight")
    while True:
        # 找到所有可见的商品卡片并点击
        # 注意：这里我们只找 "title--" 部分，因为这是用户确认可点击的
        item_elements = driver.find_elements(By.CSS_SELECTOR, 'div[class*="title--"]')
        for element in item_elements:
            try:
                # 滚动到元素使其可见，然后点击
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                time.sleep(0.1)
                element.click()
                time.sleep(0.2) # 等待JS事件触发
            except Exception as e:
                # 忽略不可点击的元素
                pass
        
        # 滚动一屏
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height
        
    print("模拟点击和滚动完成。")

    # 从JS全局变量和控制台日志中收集链接
    print("正在从浏览器日志中提取链接...")
    
    # 方案A: 从执行JS返回的全局变量获取 (更稳定)
    captured_urls = driver.execute_script("return window._captured_urls;")
    if not captured_urls:
        captured_urls = [] # 如果全局变量没有，确保是个空列表
        
    # 方案B: 从浏览器日志获取 (作为备用和补充)
    try:
        logs = driver.get_log('browser')
        for entry in logs:
            if '[拦截并抓取]' in entry['message']:
                match = re.search(r'\\[拦截并抓取\\]\\s*"(https?://[^\"]+)"', entry['message'])
                if match:
                    url = match.group(1).replace('\\u002F', '/')
                    captured_urls.append(url)
    except Exception:
        print("警告：无法从浏览器日志获取链接，可能部分链接会丢失。")


    unique_links = sorted(list(set(captured_urls)))
    print(f"发现 {len(unique_links)} 个独立的商品链接。")
    return unique_links

# --- Data Saving ---


# --- Entry Point for Other Modules ---

def scrape_shops(shops: List[dict], driver=None, save_to_csv: bool = True,
                 output_dir: Optional[str] = None) -> List[ProductData]:
    """
    Entry point for other modules to scrape shop data.

    Args:
        shops: List of shop dictionaries with 'name' and 'url' keys
        driver: Optional existing WebDriver instance. If None, creates a new one.
        save_to_csv: Whether to save the scraped data to CSV files
        output_dir: Optional output directory path for CSV files

    Returns:
        List of ProductData objects containing all scraped products
    """
    import logging
    from datetime import datetime

    # Create main output directory with timestamp
    if output_dir is None:
        output_dir = "scraped_data"

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    task_dir = os.path.join(output_dir, f"shop_scrape_{timestamp}")
    os.makedirs(task_dir, exist_ok=True)

    # Setup logging
    log_file = os.path.join(task_dir, "scraping.log")
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    logger = logging.getLogger(__name__)

    # Create products detail directory
    products_dir = os.path.join(task_dir, "products")
    os.makedirs(products_dir, exist_ok=True)

    logger.info(f"输出目录: {task_dir}")
    logger.info(f"开始处理 {len(shops)} 个店铺")

    # Create driver if not provided
    should_close_driver = False
    if driver is None:
        driver = setup_driver()
        should_close_driver = True
        # Login period
        logger.info("即将打开淘宝，如果浏览器没有自动登录，请在30秒内手动扫码登录...")
        driver.get("https://www.taobao.com")
        time.sleep(30)
        logger.info("登录时间结束，开始抓取任务。")

    all_products = []
    index_data = []  # For index.csv
    total_products_found = 0  # Track total products found

    try:
        for shop_idx, shop in enumerate(shops):
            shop_name = shop.get("name", f"店铺{shop_idx+1}")
            shop_url = shop.get("url")
            if not shop_url:
                logger.warning(f"店铺 {shop_name} 的URL为空，跳过。")
                continue

            logger.info(f"--- 正在处理店铺 {shop_idx+1}/{len(shops)}: {shop_name} ---")

            product_links = get_all_product_links_via_click_intercept(driver, shop_url)
            if not product_links:
                logger.warning(f"未能从店铺 {shop_name} 提取到任何商品链接。")
                continue

            logger.info(f"从店铺 {shop_name} 发现 {len(product_links)} 个商品")
            total_products_found += len(product_links)

            for i, link in enumerate(product_links):
                logger.info(f"  ({i+1}/{len(product_links)}) 正在处理: {link}")

                # Extract product ID from URL
                try:
                    product_id_match = re.search(r'id=(\d+)', link)
                    product_id = product_id_match.group(1) if product_id_match else f"product_{i}"
                except Exception:
                    product_id = f"product_{i}"

                # Create product directory
                product_dir = os.path.join(products_dir, product_id)
                os.makedirs(product_dir, exist_ok=True)

                # Scrape product with full detail saving
                product_data = scrape_product_data(
                    link,
                    driver=driver,
                    save_to_file=True,
                    output_folder=product_dir
                )

                if product_data:
                    all_products.append(product_data)

                    # Add to index data
                    # Extract styles and sizes information
                    styles_info = []
                    sizes_info = []
                    for style in product_data.styles:
                        style_info = f"{style.style_name} ({'有货' if style.available else '缺货'})"
                        if style.sizes:
                            sizes = [f"{size.name}({'有货' if size.available else '缺货'})" for size in style.sizes]
                            style_info += f" - {', '.join(sizes)}"
                        styles_info.append(style_info)
                        sizes_info.extend([s.name for s in style.sizes if s.available])

                    # Get price information
                    price = "N/A"
                    if product_data.product_info.price.coupon_price:
                        price = product_data.product_info.price.coupon_price
                    elif product_data.product_info.price.original_price:
                        price = product_data.product_info.price.original_price

                    index_row = {
                        "product_id": product_id,
                        "name": product_data.product_info.title,
                        "url": link,
                        "shop_name": product_data.product_info.shop.name,
                        "price": price,
                        "styles_count": len(product_data.styles),
                        "available_sizes": ", ".join(set(sizes_info)),
                        "reviews_count": len(product_data.product_details.reviews),
                        "parameters_count": len(product_data.product_details.parameters),
                        "image_details_count": len(product_data.product_details.image_details)
                    }
                    index_data.append(index_row)

                    logger.info(f"    ✓ 成功保存商品详情到: {product_dir}")
                else:
                    logger.error(f"    ✗ 未能爬取商品: {link}")

                time.sleep(1)

            # Save shop summary
            shop_file = os.path.join(task_dir, f"shop_{shop_name.replace(' ', '_')}_{len(product_links)}products.txt")
            with open(shop_file, 'w', encoding='utf-8') as f:
                f.write(f"店铺: {shop_name}\n")
                f.write(f"URL: {shop_url}\n")
                f.write(f"商品链接数: {len(product_links)}\n")
                f.write(f"成功爬取: {len([p for p in all_products if p])}\n")
                f.write("\n商品列表:\n")
                for link in product_links:
                    f.write(f"- {link}\n")

        # Save index.csv
        if save_to_csv and index_data:
            import csv
            index_file = os.path.join(task_dir, "index.csv")
            with open(index_file, 'w', newline='', encoding='utf-8-sig') as f:
                fieldnames = index_data[0].keys()
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(index_data)
            logger.info(f"✓ 索引文件已保存到: {index_file}")

        # Save task summary
        summary_file = os.path.join(task_dir, "task_summary.txt")
        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write(f"任务完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"处理的店铺数: {len(shops)}\n")
            f.write(f"发现的商品总数: {total_products_found}\n")
            f.write(f"成功爬取的商品数: {len(all_products)}\n")
            f.write(f"\n输出文件:\n")
            f.write(f"- 日志文件: scraping.log\n")
            f.write(f"- 索引文件: index.csv\n")
            f.write(f"- 商品详情: products/ 目录\n")
            f.write(f"- 每个店铺的汇总: shop_*.txt\n")

    except Exception as e:
        logger.error(f"爬取过程中发生错误: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())

    finally:
        # Close driver if we created it
        if should_close_driver:
            logger.info("所有任务完成，关闭浏览器。")
            driver.quit()

    logger.info(f"✓ 爬取任务完成! 数据保存在: {task_dir}")
    return all_products




# --- Main Execution Logic ---

def main():
    """主函数"""
    shops = load_shops_from_config()
    if not shops:
        print("配置文件中没有找到店铺信息，程序退出。")
        return

    # Use the new scrape_shops function with improved output structure
    scrape_shops(shops)

if __name__ == "__main__":
    main()
