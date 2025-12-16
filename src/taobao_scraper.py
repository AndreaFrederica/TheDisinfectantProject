import json5
import time
import csv
import re
import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

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
    """初始化并返回一个Chrome WebDriver实例"""
    options = webdriver.ChromeOptions()
    
    # 使用绝对路径解决Windows下的读写警告问题
    profile_path = os.path.abspath('chrome_profile')
    options.add_argument(f'user-data-dir={profile_path}')
    
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument('--ignore-certificate-errors')
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    return driver

# --- Scraping Core Functions ---

def scrape_all_product_details(driver, shop_url):
    """访问店铺页面，滚动加载所有商品，并提取基本信息"""
    print(f"访问店铺页面: {shop_url}")
    driver.get(shop_url)
    time.sleep(3)

    print("开始向下滚动以加载所有商品...")
    last_height = driver.execute_script("return document.body.scrollHeight")
    while True:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height
    print("商品加载完成。")

    products = []
    # 注意：这个选择器是根据新的店铺结构编写的，使用了通配符以适应动态类名
    item_elements = driver.find_elements(By.CSS_SELECTOR, 'div[class*="cardContainer"]')

    print(f"初步发现 {len(item_elements)} 个商品。开始提取详细信息...")

    for item in item_elements:
        try:
            # 在新的结构中，整个卡片可能就是一个链接，我们尝试在内部寻找 <a> 标签
            # 并不是所有 cardContainer 都是一个商品，有些是广告或其它，找不到就跳过
            link_element = item.find_element(By.TAG_NAME, "a")
            product_url = link_element.get_attribute('href')

            title_element = item.find_element(By.CSS_SELECTOR, 'div[class*="title"]')
            product_name = title_element.text.strip()
            
            price_element = item.find_element(By.CSS_SELECTOR, 'div[class*="price"]')
            # 价格被加密，这里只抓取可见的文本
            price = price_element.text.strip().replace('\n', ' ')

            products.append({
                "name": product_name,
                "price": price,
                "url": product_url,
                "stock": "未知",
                "image_url": "未知"
            })
        except Exception as e:
            # print(f"提取某个商品时出错: {e}。可能是因为商品结构不同或不是有效商品项。")
            continue
            
    return products

def scrape_detail_page(driver, product_url):
    """访问商品详情页，提取库存和主图链接"""
    details = {"stock": "获取失败", "image_url": "获取失败"}
    try:
        driver.get(product_url)
        
        # 1. 获取库存
        try:
            stock_element = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "J_EmStock"))
            )
            stock_text = stock_element.text
            stock_match = re.search(r'\d+', stock_text)
            if stock_match:
                details["stock"] = stock_match.group(0)
            else:
                details["stock"] = stock_text
        except Exception:
             # 如果找不到 J_EmStock，尝试从页面文本中搜索“库存”
            try:
                page_text = driver.find_element(By.TAG_NAME, 'body').text
                stock_match = re.search(r'库存(\d+)件', page_text)
                if stock_match:
                    details["stock"] = stock_match.group(1)
            except Exception:
                pass # 保持 "获取失败"
        
        # 2. 获取主图链接
        try:
            image_element = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "J_ImgBooth"))
            )
            details["image_url"] = image_element.get_attribute('src')
        except Exception:
            pass # 保持 "获取失败"

    except Exception as e:
        print(f"  访问详情页 {product_url} 出错: {e}")
    
    return details


# --- Data Saving ---

def save_products_to_csv(shop_name, products):
    """将商品列表保存到CSV文件"""
    if not products:
        print("没有商品信息可保存。")
        return
        
    filename = f"{shop_name.replace(' ', '_')}_{int(time.time())}.csv"
    print(f"正在将 {len(products)} 个商品保存到文件: {filename}")
    
    fieldnames = ["name", "price", "stock", "image_url", "url"]
    with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(products)
    print("保存成功。")

# --- Main Execution Logic ---

def main():
    """主函数"""
    shops = load_shops_from_config()
    if not shops:
        print("配置文件中没有找到店铺信息，程序退出。")
        return

    driver = setup_driver()

    try:
        print("即将打开淘宝，如果浏览器没有自动登录，请在30秒内手动扫码登录...")
        driver.get("https://www.taobao.com")
        time.sleep(30)
        print("登录时间结束，开始抓取任务。")

        for shop in shops:
            shop_name = shop.get("name", "未知店铺")
            shop_url = shop.get("url")
            if not shop_url:
                print(f"店铺 {shop_name} 的URL为空，跳过。")
                continue

            print(f"\n--- 正在处理店铺: {shop_name} ---")
            
            products = scrape_all_product_details(driver, shop_url)
            if not products:
                print(f"未能从店铺 {shop_name} 提取到任何商品。")
                continue

            print(f"开始为 {len(products)} 个商品获取库存和主图链接...")
            for i, product in enumerate(products):
                print(f"  ({i+1}/{len(products)}) 处理: {product['name'][:30]}...")
                details = scrape_detail_page(driver, product['url'])
                product['stock'] = details['stock']
                product['image_url'] = details['image_url']
                time.sleep(1)

            save_products_to_csv(shop_name, products)

    finally:
        print("\n所有任务完成，关闭浏览器。")
        driver.quit()

if __name__ == "__main__":
    main()