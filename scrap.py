import json
import os
import random
import logging
import time
import tempfile
import shutil
import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup

# Configure logging
logging.basicConfig(level=logging.INFO)

class ProductScraper:
    def __init__(self, url):
        # Create a unique temporary directory for user data for each session
        self.user_data_dir = tempfile.mkdtemp()

        # User agents for rotation
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Gecko/20100101 Firefox/89.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36",
            # Add more user agents as needed
        ]

        # Chrome options setup
        chrome_options = Options()
        chrome_options.add_argument("--headless")  # Run headlessly
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument(f"--user-data-dir={self.user_data_dir}")  # Unique user data dir
        chrome_options.add_argument(f"user-agent={random.choice(self.user_agents)}")

        # Initialize WebDriver with options
        self.driver = webdriver.Chrome(options=chrome_options)
        self.url = url
        
    def find_product_containers(self, soup):
        """Improved version: Target Amazon's s-search-result containers and exclude sponsored items."""
        try:
            elements = soup.find_all("div", {"data-component-type": "s-search-result"})
            clean_cards_html = [elem for elem in elements if not elem.find(string=re.compile("Sponsored", re.IGNORECASE))]

            selenium_elements = []
            for i, card in enumerate(clean_cards_html[:10]):
                try:
                    sel_elem = self.driver.find_element(By.XPATH, f"(//div[@data-component-type='s-search-result'])[position()={i+1}]")
                    selenium_elements.append(sel_elem)
                except:
                    continue

            print(f"Matched {len(selenium_elements)} Selenium elements")
            return selenium_elements
        except Exception as e:
            print(f"Error finding containers: {e}")
            return []

    def extract_from_container(self, product):
        """Extract name, brand, price with improved logic"""
        try:
            all_elements = product.find_elements(By.XPATH, ".//*[text()]")
            name = "Not found"
            brand = "Not found"
            price = "Not found"
            
            price_pattern = r"[\$£€¥₹₨][0-9]+[.,]?[0-9]*"  # Requires currency symbol
            name_pattern = r"^[A-Za-z0-9].{10,}$"  # Stricter for longer product names
            brand_pattern = r"^[A-Za-z]{2,}$"
            
            days_of_week = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
            skip_phrases = ["ships to", "featured", "sponsored", "see more", "out of stock", "add to cart", 
                           "free shipping", "delivery", "arrive", "get it by", "advertisement", "promo", 
                           "deal", "delivering to"]
            
            for elem in all_elements:
                text = elem.text.strip().lower()
                class_name = elem.get_attribute("class").lower()
                tag_name = elem.tag_name.lower()
                original_text = elem.text.strip()
                
                if any(phrase in text for phrase in skip_phrases):
                    continue
                
                # Skip <a> tags to avoid ads
                if tag_name == 'a':
                    continue
                
                # Price detection
                if (re.search(price_pattern, text) or any(kw in class_name for kw in ["price", "cost", "sale", "amount", "money", "currency"])) and len(text) <= 20:
                    if not any(day in text for day in days_of_week):
                        price = original_text
                
                # Name detection
                elif (re.search(name_pattern, text) or any(kw in class_name for kw in ["title", "name", "product", "item"]) or tag_name in ["h2", "h3"]) and len(text) > 10:
                    if name == "Not found" or len(text) > len(name):
                        name = original_text
                
                # Brand detection
                elif (re.search(brand_pattern, text) or any(kw in class_name for kw in ["brand", "by", "vendor", "maker"])) and len(text) < 20:
                    if not any(kw in text for kw in ["sponsored", "usb", "office", "delivery", "ship", "arrive", "ad", "promo"]) and not any(day in text for day in days_of_week):
                        brand = original_text
            
            # Fallbacks with stricter rules
            if name == "Not found":
                name_candidates = [e.text.strip() for e in all_elements 
                                  if len(e.text.strip()) > 10 
                                  and not re.search(price_pattern, e.text.lower()) 
                                  and not any(phrase in e.text.lower() for phrase in skip_phrases) 
                                  and e.tag_name != 'a']
                name = name_candidates[0] if name_candidates else "Not found"
            
            if price == "Not found":
                price_candidates = [e.text.strip() for e in all_elements 
                                   if re.search(r"[\$£€¥₹₨][0-9]+", e.text) 
                                   and len(e.text.strip()) <= 20 
                                   and not any(day in e.text.lower() for day in days_of_week) 
                                   and e.tag_name != 'a']
                price = price_candidates[0] if price_candidates else "Not found"
            
            if brand == "Not found":
                # Infer brand from name if possible
                if name != "Not found" and " " in name:
                    brand = re.match(r"^[A-Za-z]+", name).group(0) if re.match(r"^[A-Za-z]+", name) else "Not found"
                else:
                    brand_candidates = [e.text.strip() for e in all_elements 
                                       if re.search(brand_pattern, e.text) 
                                       and len(e.text.strip()) < 20 
                                       and not any(kw in e.text.lower() for kw in ["sponsored", "usb", "office", "delivery", "ship", "arrive", "ad", "promo"]) 
                                       and not any(day in text.lower() for day in days_of_week) 
                                       and e.tag_name != 'a']
                    brand = brand_candidates[0] if brand_candidates else "Not found"
            
            return {"name": name, "Brand": brand, "list_price": price}
        except Exception as e:
            print(f"Extraction error: {e}")
            return {"name": "Not found", "Brand": "Not found", "list": "Not found"}

    def scrape_products(self, url, max_products=10):
        try:
            base_url = url.split('#')[0] if '#' in url else url
            print(f"Navigating to base URL: {base_url}")
            self.driver.get(base_url)
            time.sleep(5)
            
            print(f"Current URL: {self.driver.current_url}")
            print("Scrolling to load content...")
            for _ in range(3):
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(3)
            
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            print("Analyzing page source for product containers...")
            products = self.find_product_containers(soup)
            if not products:
                raise Exception("No product containers detected")
                
            print(f"Found {len(products)} potential product cards")
            products = products[:max_products]
            
            products_data = []
            for i, product in enumerate(products, 1):
                try:
                    print(f"Scraping product {i}...")
                    data = self.extract_from_container(product)
                    if data["name"] != "Not found" and data["list_price"] != "Not found":
                        products_data.append(data)
                        print(f"Extracted - name: {data['name']}, Brand: {data['Brand']}, list_price: {data['list_price']}")
                    else:
                        print(f"Skipped product {i}: insufficient data")
                except Exception as e:
                    print(f"Error scraping product {i}: {e}")
            
            return products_data
            
        except Exception as e:
            print(f"Error during scraping: {str(e)}")
            print("Page source sample:")
            print(self.driver.page_source[:1000])
            return []
            
    def save_to_json(self, data, filename="products.json"):
        """Save data to a JSON file"""
        if data:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            print(f"Data saved to {filename}")
        else:
            print("No data to save")

    def close(self):
        self.driver.quit()

def main():
    target_url = input("Enter the product website URL to scrape: ").strip()
    if not target_url.startswith(('http://', 'https://')):
        target_url = 'https://' + target_url
    
    scraper = ProductScraper()
    print(f"Scraping products from {target_url}")
    products = scraper.scrape_products(target_url, max_products=10)
    
    if products:
        print("\nScraped Products:")
        print("-" * 50)
        for i, product in enumerate(products, 1):
            print(f"Product {i}:")
            print(f"name: {product['name']}")
            print(f"Brand: {product['Brand']}")
            print(f"list_price: {product['list_price']}")
            print("-" * 50)
    else:
        print("No products were scraped. Check the URL or page content.")
    
    scraper.save_to_json(products)
    scraper.close()

if __name__ == "__main__":
    try:
        import selenium
        import pandas
        import bs4
        import json
    except ImportError as e:
        print(f"Missing required package: {e}")
        print("Please install requirements:")
        print("pip install selenium pandas beautifulsoup4")
        exit()
        
    main()