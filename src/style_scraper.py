
import json
from bs4 import BeautifulSoup

def scrape_styles(html_content):
    """
    Scrapes product style information from the given HTML content.

    Args:
        html_content (str): The HTML content of the product page.

    Returns:
        dict: A dictionary containing the extracted style information.
    """
    soup = BeautifulSoup(html_content, 'html.parser')

    styles = []
    sizes = []

    # Find the "颜色分类" (Color Classification) section
    color_section = soup.find('div', class_='skuItem--Z2AJB9Ew', text=lambda t: t and '颜色分类' in t)
    if not color_section:
        color_section = soup.find(lambda tag: tag.name == 'span' and '颜色分类' in tag.text and 'f-els-2' in tag.get('class', []))
        if color_section:
            color_section = color_section.find_parent('div', class_='skuItem--Z2AJB9Ew')

    if color_section:
        for item in color_section.find_all('div', class_='valueItem--smR4pNt4'):
            style_name_tag = item.find('span', class_='valueItemText--T7YrR8tO')
            style_name = style_name_tag['title'] if style_name_tag else 'N/A'

            img_tag = item.find('img', class_='valueItemImg--GC9bH5my')
            img_url = img_tag['src'] if img_tag else 'N/A'

            styles.append({
                'name': style_name,
                'image_url': img_url
            })

    # Find the "尺码" (Size) section
    size_section = soup.find('div', class_='skuItem--Z2AJB9Ew', text=lambda t: t and '尺码' in t)
    if not size_section:
        size_section = soup.find(lambda tag: tag.name == 'span' and '尺码' in tag.text and 'f-els-2' in tag.get('class', []))
        if size_section:
            size_section = size_section.find_parent('div', class_='skuItem--Z2AJB9Ew')
            
    if size_section:
        for item in size_section.find_all('div', class_='valueItem--smR4pNt4'):
            size_tag = item.find('span', class_='valueItemText--T7YrR8tO')
            if size_tag:
                sizes.append(size_tag['title'])

    return {
        'styles': styles,
        'sizes': sizes
    }

if __name__ == '__main__':
    # Read the HTML file
    with open('html/款式选择.html', 'r', encoding='utf-8') as f:
        html_content = f.read()

    # Scrape the data
    data = scrape_styles(html_content)

    # Print the data as JSON
    print(json.dumps(data, indent=2, ensure_ascii=False))
