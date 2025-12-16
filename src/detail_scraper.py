import re
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def scrape_product_detail_page(driver, product_url):
    """
    在单个商品详情页上，提取所有需要的信息（标题、价格、库存、主图）。
    """
    product_data = {
        "name": "获取失败", "price": "获取失败", "stock": "获取失败", 
        "image_url": "获取失败", "url": product_url
    }
    try:
        driver.get(product_url)
        
        # 1. 获取标题 (使用详情页的新选择器)
        try:
            title_element = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'div[class*="MainTitle"]'))
            )
            product_data["name"] = title_element.text.strip()
        except Exception:
            print(f"  - 获取标题失败")

        # 2. 获取价格 (价格通常是动态的，尽力而为)
        try:
            price_element = driver.find_element(By.CSS_SELECTOR, 'div[class*="highlightPrice"] span[class*="text"]')
            product_data["price"] = price_element.text.strip()
        except Exception:
             print(f"  - 获取价格失败")

        # 3. 获取库存
        try:
            stock_element = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.ID, "J_EmStock"))
            )
            stock_text = stock_element.text
            stock_match = re.search(r'\d+', stock_text)
            if stock_match:
                product_data["stock"] = stock_match.group(0)
            else:
                product_data["stock"] = stock_text
        except Exception:
            try:
                # 备用方案：寻找页面上任何地方的 "有货" 或 "库存XX件"
                body_text = driver.find_element(By.TAG_NAME, 'body').text
                if "有货" in body_text:
                    product_data["stock"] = "有货"
                else:
                    stock_match = re.search(r'库存(\d+)件', body_text)
                    if stock_match:
                        product_data["stock"] = stock_match.group(1)
            except Exception:
                 print(f"  - 获取库存失败")
        
        # 4. 获取主图链接 (使用详情页的新选择器)
        try:
            # 优先使用带mainPicImageEl ID的图片
            image_element = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.ID, "mainPicImageEl"))
            )
            product_data["image_url"] = image_element.get_attribute('src')
        except Exception:
            try:
                # 备用方案
                image_element = driver.find_element(By.ID, "J_ImgBooth")
                product_data["image_url"] = image_element.get_attribute('src')
            except Exception:
                print(f"  - 获取主图失败")

    except Exception as e:
        print(f"  访问详情页 {product_url} 发生严重错误: {e}")
    
    return product_data
