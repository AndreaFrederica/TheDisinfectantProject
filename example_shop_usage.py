"""
Example usage of taobao_scraper module

This demonstrates how other modules can import and use the scrape_shops function
to get structured product data from multiple shops.
"""

from src.taobao_scraper import scrape_shops, setup_driver

def example_usage():
    """Example of how to use the shop scraper from another module."""

    # Example shops list (you would get this from your config or database)
    shops = [
        {
            "name": "测试店铺1",
            "url": "https://shop1.taobao.com"
        },
        {
            "name": "测试店铺2",
            "url": "https://shop2.taobao.com"
        }
    ]

    # Option 1: Simple usage - let the scraper handle the driver
    print("=== Option 1: Simple usage ===")
    all_products = scrape_shops(
        shops=shops,
        save_to_csv=True,
        output_dir="shop_output"
    )

    # Process the results
    total_products = len(all_products)
    print(f"\nTotal products scraped: {total_products}")

    if all_products:
        # Example: Find all products with available styles
        available_products = []
        for product in all_products:
            for style in product.styles:
                if style.available and style.sizes:
                    # Check if any size is available
                    if any(size.available for size in style.sizes):
                        available_products.append({
                            "title": product.product_info.title,
                            "style": style.style_name,
                            "shop": product.product_info.shop.name
                        })
                        break

        print(f"Products with available items: {len(available_products)}")

        # Example: Export to custom format
        custom_export = []
        for product in all_products:
            custom_export.append({
                "product_id": product.product_info.url.split("id=")[-1].split("&")[0],
                "title": product.product_info.title,
                "shop_name": product.product_info.shop.name,
                "price": product.product_info.price.coupon_price or product.product_info.price.original_price,
                "review_count": len(product.product_details.reviews),
                "styles": len(product.styles)
            })

        # Save custom format
        import json
        with open("custom_products.json", "w", encoding="utf-8") as f:
            json.dump(custom_export, f, indent=2, ensure_ascii=False)

    # Option 2: Use existing driver instance (for batch processing)
    print("\n=== Option 2: Batch processing with shared driver ===")
    # This would be useful when scraping many shops or integrating with other scrapers
    # driver = setup_driver()
    # try:
    #     # Login manually once
    #     driver.get("https://www.taobao.com")
    #     input("Please login manually and press Enter to continue...")
    #
    #     # Scrape multiple shops with the same driver
    #     products = scrape_shops(shops, driver=driver, save_to_csv=False)
    #     print(f"Scraped {len(products)} products")
    #
    # finally:
    #     driver.quit()

    # Option 3: Scraping a single shop
    print("\n=== Option 3: Single shop scraping ===")
    # single_shop = [shops[0]]  # Take only the first shop
    # single_shop_products = scrape_shops(
    #     single_shop,
    #     save_to_csv=True,
    #     output_dir="single_shop_output"
    # )

if __name__ == "__main__":
    example_usage()