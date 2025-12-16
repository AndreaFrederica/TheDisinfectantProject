import json5
import time
import csv
import re
import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from detail_scraper import scrape_product_detail_page

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
    
    # 开启浏览器日志记录
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
    
    service = Service(ChromeDriverManager().install())
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
            
            product_links = get_all_product_links_via_click_intercept(driver, shop_url)
            if not product_links:
                print(f"未能从店铺 {shop_name} 提取到任何商品链接。")
                continue

            all_products_data = []
            print(f"开始访问 {len(product_links)} 个商品详情页以提取完整信息...")
            for i, link in enumerate(product_links):
                print(f"  ({i+1}/{len(product_links)}) 正在处理: {link}")
                product_data = scrape_product_detail_page(driver, link)
                all_products_data.append(product_data)
                time.sleep(1)

            save_products_to_csv(shop_name, all_products_data)

    finally:
        print("\n所有任务完成，关闭浏览器。")
        driver.quit()

if __name__ == "__main__":
    main()
