# -*- coding: utf-8 -*-
import requests
from bs4 import BeautifulSoup
import csv
import time
from urllib.parse import urljoin
import random
from urllib.robotparser import RobotFileParser

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
]

def get_random_user_agent():
    return random.choice(USER_AGENTS)

def check_robots(base_url):
    rp = RobotFileParser()
    rp.set_url(urljoin(base_url, '/robots.txt'))
    try:
        rp.read()
        print(f"Successfully read robots.txt from {base_url}")
    except Exception as e:
        print(f"Error reading robots.txt: {e}")
        return None
    return rp

def can_fetch(rp, url):
    if rp is None:
        return True
    allowed = rp.can_fetch(get_random_user_agent(), url)
    print(f"Can fetch {url}: {allowed}")
    return allowed

def scrape_product_details(product_url, rp):
    if not can_fetch(rp, product_url):
        print(f"Blocked by robots.txt: {product_url}")
        return "N/A"

    try:
        headers['User-Agent'] = get_random_user_agent()
        response = requests.get(product_url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # Broaden description search
        desc = (soup.find('div', class_='product-description') or
                soup.find('div', class_='description') or
                soup.find('div', class_='product-attribute-overview') or
                soup.find('div', id='description') or
                soup.find('div', class_='product-details') or  # Added fallback
                soup.find('meta', attrs={'name': 'description'}))  # Fallback to meta tag
        desc_text = desc.get_text(strip=True) if desc and hasattr(desc, 'get_text') else desc['content'] if desc else "N/A"
        print(f"Description for {product_url}: {desc_text[:50]}...")  # Log snippet
        return desc_text

    except requests.RequestException as e:
        print(f"Error fetching {product_url}: {e}")
        return "N/A"

def scrape_products_from_page(url, rp):
    if not can_fetch(rp, url):
        print(f"Blocked by robots.txt: {url}")
        return [], None

    try:
        headers['User-Agent'] = get_random_user_agent()
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        product_container = (soup.find('div', class_='products-grid') or
                             soup.find('ul', class_='products-grid') or
                             soup.find('div', class_='product-items'))
        if not product_container:
            print(f"No product container on {url}. Dumping HTML.")
            with open('page_debug.html', 'w', encoding='utf-8') as f:
                f.write(soup.prettify())
            return [], None

        products = product_container.find_all('li', class_='product') or product_container.find_all('div', class_='product')  # Broaden search
        if not products:
            print(f"No products found on {url}. Container HTML:")
            print(product_container.prettify()[:2000])
            return [], None

        inventory = []
        for product in products:
            details = product.find('div', class_='product-item-details') or product  # Fallback to product itself
            name = details.find('a', class_='product-item-link') or details.find('a')
            name_text = name.get_text(strip=True) if name else "N/A"
            product_url = name['href'] if name and 'href' in name.attrs else url

            price_box = details.find('span', class_='price-wrapper') or details.find('span', class_='price')
            price_text = (price_box.find('span', class_='price').get_text(strip=True) if price_box and price_box.find('span', class_='price')
                          else price_box['data-price-amount'] if price_box and 'data-price-amount' in price_box.attrs else "N/A")
            if price_text != "N/A" and not price_text.startswith('USD'):
                price_text = f"USD {price_text}"

            stock = details.find('span', class_=lambda x: x and 'stock' in x) or details.find('p', class_='stock')
            stock_text = stock.get_text(strip=True) if stock else "Unknown"

            desc_text = scrape_product_details(product_url, rp) if name_text != "N/A" else "N/A"

            if name_text != "N/A":
                inventory.append({
                    "Name": name_text,
                    "Price": price_text,
                    "Stock": stock_text,
                    "URL": product_url,
                    "Description": desc_text
                })

        next_link = soup.find('a', class_='next') or soup.find('a', rel='next')
        next_url = urljoin(url, next_link['href']) if next_link and 'href' in next_link.attrs else None
        print(f"Found {len(inventory)} products on {url}. Next page: {next_url}")
        return inventory, next_url

    except requests.RequestException as e:
        print(f"Error fetching {url}: {e}")
        return [], None

def scrape_category(url, base_url, rp):
    all_inventory = []
    current_url = url
    while current_url:
        print(f"Scraping: {current_url}")
        page_inventory, next_url = scrape_products_from_page(current_url, rp)
        all_inventory.extend(page_inventory)
        current_url = next_url
        time.sleep(random.uniform(2, 5))
    return all_inventory

def scrape_site(start_url):
    rp = check_robots(start_url)
    if not can_fetch(rp, start_url):
        print(f"Blocked by robots.txt: {start_url}")
        return []

    try:
        headers['User-Agent'] = get_random_user_agent()
        response = requests.get(start_url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        category_links = set()
        for link in soup.find_all('a', href=True):
            href = link['href']
            if any(x in href for x in ['/msasa_store/', '/categories/', '/shop/', '/product-category/', '/products/', '/product/']):
                full_url = urljoin(start_url, href)
                category_links.add(full_url)

        if not category_links:
            print("No categories found. Dumping HTML.")
            with open('debug.html', 'w', encoding='utf-8') as f:
                f.write(soup.prettify())
            return []

        print(f"Found {len(category_links)} categories: {list(category_links)[:5]}...")
        all_inventory = []
        for cat_url in category_links:
            all_inventory.extend(scrape_category(cat_url, start_url, rp))
        print(f"Total products scraped: {len(all_inventory)}")
        return all_inventory

    except requests.RequestException as e:
        print(f"Error fetching {start_url}: {e}")
        return []

def save_to_csv(data, filename="full_inventory.csv"):
    if not data:
        print("No data to save!")
        return
    keys = data[0].keys()
    try:
        with open(filename, 'w', newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=keys)
            writer.writeheader()
            writer.writerows(data)
        print(f"Saved {len(data)} items to {filename}")
    except Exception as e:
        print(f"Error saving CSV: {e}")

if __name__ == "__main__":
    start_url = input("Enter the homepage URL to scrape (e.g., https://halsteds.co.zw/): ").strip()
    if not start_url:
        print("No URL provided. Exiting.")
    else:
        inventory_data = scrape_site(start_url)
        if inventory_data:
            for item in inventory_data[:5]:  # Show first 5 for brevity
                print(f"Product: {item['Name']}, Price: {item['Price']}, Description: {item['Description'][:50]}...")
            save_to_csv(inventory_data)
        else:
            print("No inventory data retrieved.")