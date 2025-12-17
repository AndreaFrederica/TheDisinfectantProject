"""
Example usage of single_product_scraper module

This demonstrates how other modules can import and use the scrape_product_data function
to get structured product data.
"""

from src.single_product_scraper import scrape_product_data, ProductData
import json

def example_usage():
    """Example of how to use the scraper from another module."""

    # Example product URL (you would get this from your shop scraper)
    product_url = "https://item.taobao.com/item.htm?id=853761881909"

    # Option 1: Simple usage - let the scraper handle the driver
    print("=== Option 1: Simple usage ===")
    product_data = scrape_product_data(product_url)

    if product_data:
        # Access structured data
        print(f"Product Title: {product_data.product_info.title}")
        print(f"Shop Name: {product_data.product_info.shop.name}")
        print(f"Number of styles: {len(product_data.styles)}")

        # Access first style information
        if product_data.styles:
            first_style = product_data.styles[0]
            print(f"\nFirst style: {first_style.style_name}")
            print(f"Available: {first_style.available}")
            print(f"Sizes: {[size.name for size in first_style.sizes]}")

        # Convert to dictionary if needed
        product_dict = {
            "title": product_data.product_info.title,
            "shop": product_data.product_info.shop.name,
            "styles": [
                {
                    "name": style.style_name,
                    "available": style.available,
                    "sizes": [{"name": size.name, "available": size.available} for size in style.sizes]
                }
                for style in product_data.styles
            ]
        }

        # Save to custom location
        with open("custom_product_data.json", "w", encoding="utf-8") as f:
            json.dump(product_dict, f, indent=2, ensure_ascii=False)

    # Option 2: Use existing driver instance (for batch processing)
    print("\n=== Option 2: Batch processing with shared driver ===")
    # This would be useful when scraping multiple products
    # from src.single_product_scraper import setup_driver

    # driver = setup_driver()
    # try:
    #     urls = [
    #         "https://item.taobao.com/item.htm?id=853761881909",
    #         "https://item.taobao.com/item.htm?id=another_id"
    #     ]
    #     for url in urls:
    #         data = scrape_product_data(url, driver=driver, save_to_file=False)
    #         if data:
    #             print(f"Scraped: {data.product_info.title}")
    # finally:
    #     driver.quit()

    # Option 3: Use shared driver but let function close it when done
    # print("\n=== Option 3: Let function close driver ===")
    # driver = setup_driver()
    # scrape_product_data(url, driver=driver, close_driver=True)  # Driver will be closed automatically

    # Option 4: Save to specific folder
    print("\n=== Option 4: Save to specific folder ===")
    # product_data = scrape_product_data(
    #     product_url,
    #     save_to_file=True,
    #     output_folder="my_custom_output_folder"
    # )

if __name__ == "__main__":
    example_usage()