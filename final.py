import requests
from bs4 import BeautifulSoup
import csv
import logging
import time
from urllib.parse import urljoin
import json
import re
from rich.logging import RichHandler
from rich.console import Console
import concurrent.futures

# Настройка Rich
console = Console()
logging.basicConfig(
    level=logging.DEBUG,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(console=console, markup=True)]
)
logger = logging.getLogger("rich")

def fetch_html(url):
    """Получение HTML-страницы."""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        response.encoding = 'utf-8'
        logger.info(f"[green]Загружена страница[/green] {url}")
        return response.text
    except requests.exceptions.RequestException as e:
        logger.error(f"[red]Ошибка загрузки[/red] {url}: {e}")
        return None

def parse_catalog(url, start_page, end_page):
    """Извлечение ссылок на товары из нескольких страниц каталога."""
    product_links = []
    for page in range(start_page, end_page + 1):
        page_url = f"{url}?PAGEN_1={page}"
        logger.info(f"[blue]Обработка страницы каталога[/blue]: {page_url}")
        html = fetch_html(page_url)
        if not html:
            continue

        soup = BeautifulSoup(html, 'html.parser')
        for link in soup.find_all('a', href=True):
            full_url = urljoin(url, link['href'])
            if full_url.startswith("https://zumus.ru/product/"):
                product_links.append(full_url)
        time.sleep(1)

    logger.info(f"[cyan]Найдено {len(product_links)} товаров.[/cyan]")
    return list(set(product_links))  # Убираем дубликаты

def extract_category(soup):
    """Извлечение категории товара."""
    category_elements = soup.find_all("span", itemprop="name")
    if category_elements:
        categories = " / ".join([element.get_text(strip=True) for element in category_elements])
        if "Артикул" in categories:
            categories = categories.split(" / Артикул")[0]
        return categories
    return "Категория отсутствует"

def extract_price(soup):
    """Извлечение цены товара."""
    price_element = soup.find("span", class_="price_value")
    if price_element:
        return price_element.get_text(strip=True)
    return "Цена отсутствует"

def extract_images(soup, base_url):
    """Извлечение ссылок на изображения товара."""
    images = []
    photo_elements = soup.find_all('li', id=re.compile(r'photo-\d+'))
    for element in photo_elements:
        img_tag = element.find('img')
        if img_tag:
            image_url = img_tag.get('data-src') or img_tag.get('src')
            if image_url and image_url.startswith('/upload'):
                image_url = urljoin(base_url, image_url)
            images.append(image_url)
    logger.info(f"[green]Найдено {len(images)} изображений.[/green]")
    return images

def extract_description(soup):
    """Извлечение описания товара."""
    description_element = soup.find("div", class_="descr-outer-wrapper")
    if description_element:
        text_elements = description_element.find_all(['p', 'li', 'h2', 'h3'])
        description = "\n".join([element.get_text(strip=True) for element in text_elements if element.get_text(strip=True)])
        return description
    return "Описание отсутствует"

def clean_text(text):
    """Удаление лишних пустых строк."""
    lines = text.splitlines()
    cleaned_lines = [line.strip() for line in lines if line.strip()]
    return "\n".join(cleaned_lines)

def parse_characteristics(soup):
    """Парсинг характеристик."""
    characteristics_element = soup.find("div", class_="top_props")
    if characteristics_element:
        characteristics_text = clean_text(characteristics_element.get_text())
        keywords = ["Вес", "Размер упаковки", "Доступные варианты", "Фасовка", "UPC Код"]
        for keyword in keywords:
            characteristics_text = re.sub(f"(?<!\\n)({keyword})", r"\n\1", characteristics_text)
        return characteristics_text.strip()
    return "Характеристики отсутствуют"

def extract_additional_description(soup):
    """Извлечение дополнительного описания товара."""
    additional_desc = []
    table_rows = soup.find_all('tr', valign='top')
    for row in table_rows:
        cells = row.find_all('td')
        if len(cells) == 2:
            key = cells[0].get_text(strip=True)
            value = cells[1].get_text(strip=True)
            additional_desc.append(f"{key}: {value}")
        elif len(cells) == 3:
            key = cells[0].get_text(strip=True)
            value = cells[1].get_text(strip=True)
            percent = cells[2].get_text(strip=True)
            additional_desc.append(f"{key}: {value} ({percent})")
        elif len(cells) == 1:
            key = cells[0].get_text(strip=True)
            additional_desc.append(f"{key}: ")

    return "\n".join(additional_desc) if additional_desc else "Дополнительное описание отсутствует"

def auto_detect_and_parse(soup, base_url):
    """Извлечение данных о товаре."""
    data = {
        'CATEGORY': {'data': extract_category(soup)},
        'Название': {'data': soup.find("h1", id="pagetitle").get_text(strip=True) if soup.find("h1", id="pagetitle") else 'Название отсутствует'},
        'Цена': {'data': extract_price(soup)},
        'Ссылки на изображения': {'data': extract_images(soup, base_url)},
        'Характеристики': {'data': parse_characteristics(soup)},
        'Артикул': {'data': soup.find("div", class_="article iblock", itemprop="additionalProperty").get_text(strip=True) if soup.find("div", class_="article iblock", itemprop="additionalProperty") else 'Артикул отсутствует'},
        'Описание': {'data': extract_description(soup)},
        'Дополнительное описание': {'data': extract_additional_description(soup)}
    }
    return data

def parse_product(url):
    """Извлечение информации о товаре."""
    html = fetch_html(url)
    if not html:
        return None

    soup = BeautifulSoup(html, 'html.parser')
    try:
        return auto_detect_and_parse(soup, url)
    except Exception as e:
        logger.error(f"[red]Ошибка извлечения данных с {url}: {e}[/red]")
        return None

def save_to_csv(products, filename):
    """Сохранение списка товаров в CSV."""
    with open(filename, 'w', newline='', encoding='utf-8') as file:
        fieldnames = [
            'Product Code', 'Product Name', 'Category', 'Price',
            'Description', 'Additional Description', 'Image URL', 'Features'
        ]
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for product in products:
            row = {
                'Product Code': product.get('Артикул', {}).get('data', ''),
                'Product Name': product.get('Название', {}).get('data', ''),
                'Category': product.get('CATEGORY', {}).get('data', ''),
                'Price': product.get('Цена', {}).get('data', ''),
                'Description': product.get('Описание', {}).get('data', ''),
                'Additional Description': product.get('Дополнительное описание', {}).get('data', ''),
                'Image URL': "\n".join(product.get('Ссылки на изображения', {}).get('data', [])),
                'Features': product.get('Характеристики', {}).get('data', '')
            }
            writer.writerow(row)
    logger.info(f"[green]Данные сохранены в {filename}[/green]")

def save_to_json(products, filename):
    """Сохранение списка товаров в JSON."""
    with open(filename, 'w', encoding='utf-8') as file:
        json.dump(products, file, ensure_ascii=False, indent=4)
    logger.info(f"[green]Данные сохранены в {filename}[/green]")

def main():
    catalog_url = "https://zumus.ru/catalog"
    output_csv = "products.csv"
    output_json = "products.json"
    start_page = 1
    end_page = 1

    product_links = parse_catalog(catalog_url, start_page, end_page)
    logger.info(f"[yellow]Парсинг данных о {len(product_links)} товарах...[/yellow]")

    products = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_url = {executor.submit(parse_product, url): url for url in product_links}
        for future in concurrent.futures.as_completed(future_to_url):
            product_data = future.result()
            if product_data:
                products.append(product_data)

    save_to_csv(products, output_csv)
    save_to_json(products, output_json)

if __name__ == "__main__":
    main()
