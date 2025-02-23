# -*- coding: utf-8 -*-
"""
Created on Fri Feb 21 21:03:49 2025

@author: Busiso
"""
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
    except Exception as e:
        print(f"Error reading robots.txt: {e}")
        return None
    return rp

def can_fetch(rp, url):
    if rp is None:
        return True
    return rp.can_fetch(get_random_user_agent(), url)

def scrape_product_details(product_url, rp):
    if rp and not can_fetch(rp, product_url):
        print(f"Not allowed to scrape {product_url} per robots.txt")
        return "N/A"

    try:
        headers['User-Agent'] = get_random_user_agent()
        response = requests.get(product_url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # Look for description (common Magento locations)
        desc = (soup.find('div', class_='product-description') or
                soup.find('div', class_='description') or
                soup.find('div', class_='product-attribute-overview') or
                soup.find('div', id='description'))
        desc_text = desc.get_text(strip=True) if desc else "N/A"

        return desc_text

    except requests.RequestException as e:
        print(f"Error fetching product page {product_url}: {e}")
        return "N/A"

def scrape_products_from_page(url, rp):
    if rp and not can_fetch(rp, url):
        print(f"Not allowed to scrape {url} per robots.txt")
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
            print(f"No product container on {url}. Dumping to 'page_debug.html'")
            with open('page_debug.html', 'w', encoding='utf-8') as f:
                f.write(soup.prettify())
            return [], None

        products = product_container.find_all('li', class_='product')
        if not products:
            print(f"No 'li.product' found on {url}. Container HTML:")
            print(product_container.prettify()[:2000])
            return [], None

        inventory = []
        for i, product in enumerate(products, 1):
            html_snippet = product.prettify()[:1500]
            print(f"Product {i} HTML from {url}:\n{html_snippet}")

            details = product.find('div', class_='product-item-details')
            if details:
                name = details.find('a', class_='product-item-link')
                name_text = name.get_text(strip=True) if name else "N/A"
                product_url = name['href'] if name and 'href' in name.attrs else url

                price_box = details.find('span', class_='price-wrapper')
                price_text = (price_box.find('span', class_='price').get_text(strip=True) if price_box and price_box.find('span', class_='price')
                              else price_box['data-price-amount'] if price_box and 'data-price-amount' in price_box.attrs else "N/A")
                if price_text != "N/A" and not price_text.startswith('USD'):
                    price_text = f"USD {price_text}"

                stock = (details.find('span', class_=lambda x: x and 'stock' in x) or
                         details.find('p', class_='stock') or
                         product.find('div', class_='stock'))
                stock_text = stock.get_text(strip=True) if stock else "Unknown"

                # Scrape description from product page
                desc_text = scrape_product_details(product_url, rp) if name_text != "N/A" else "N/A"
            else:
                name_text, price_text, stock_text, desc_text, product_url = "N/A", "N/A", "Unknown", "N/A", url

            if name_text != "N/A":
                inventory.append({
                    "Name": name_text,
                    "Price": price_text,
                    "Stock": stock_text,
                    "URL": product_url,  # Use product-specific URL
                    "Description": desc_text
                })

        next_link = soup.find('a', class_='next')
        next_url = next_link['href'] if next_link and 'href' in next_link.attrs else None
        if next_url and not next_url.startswith('http'):
            next_url = urljoin(url, next_url)
        print(f"Next page URL: {next_url}")

        return inventory, next_url

    except requests.RequestException as e:
        print(f"Error fetching {url}: {e}")
        return [], None

def scrape_category(url, base_url, rp):
    all_inventory = []
    current_url = url

    while current_url:
        print(f"Scraping category page: {current_url}")
        page_inventory, next_url = scrape_products_from_page(current_url, rp)
        all_inventory.extend(page_inventory)
        current_url = next_url
        time.sleep(random.uniform(2, 5))

    return all_inventory

def scrape_site(start_url):
    rp = check_robots(start_url)
    if rp and not can_fetch(rp, start_url):
        print(f"Not allowed to scrape {start_url} per robots.txt")
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
            print("No category links found! Dumping to 'debug.html'")
            with open('debug.html', 'w', encoding='utf-8') as f:
                f.write(soup.prettify())
            return []

        print(f"Found {len(category_links)} category/store links: {list(category_links)[:5]}...")
        all_inventory = []
        for i, cat_url in enumerate(category_links, 1):
            print(f"Processing category {i}/{len(category_links)}: {cat_url}")
            cat_inventory = scrape_category(cat_url, start_url, rp)
            all_inventory.extend(cat_inventory)

        return all_inventory

    except requests.RequestException as e:
        print(f"Error fetching homepage {start_url}: {e}")
        return []

def save_to_csv(data, filename="full_inventory.csv"):
    if not data:
        print("No data to save.")
        return
    keys = data[0].keys()
    with open(filename, 'w', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=keys)
        writer.writeheader()
        writer.writerows(data)
    print(f"Data saved to {filename}")

if __name__ == "__main__":
    start_url = input("Enter the homepage URL to scrape (e.g., https://halsteds.co.zw/): ").strip()
    if not start_url:
        print("No URL provided. Exiting.")
    else:
        inventory_data = scrape_site(start_url)
        if inventory_data:
            for item in inventory_data:
                print(f"Product: {item['Name']}, Price: {item['Price']}, Stock: {item['Stock']}, URL: {item['URL']}, Description: {item['Description']}")
            save_to_csv(inventory_data)
        else:
            print("No inventory data retrieved.")