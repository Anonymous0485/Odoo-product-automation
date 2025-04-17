from fastapi import FastAPI
import requests
from amazon_modified import ProductScraper
import json

app = FastAPI()

ENDPOINT_URL = "https://testingerp.argentek.org/product/create"

@app.get("/")
def root():
    return {"message": "Amazon scraper & uploader is ready."}

@app.post("/scrape-and-upload")
def scrape_and_upload(url: str):
    scraper = ProductScraper()
    scraped_data = scraper.scrape_products(url, max_products=10)
    scraper.save_to_json(scraped_data, filename="products.json")
    scraper.close()

    if not scraped_data:
        return {"status": "error", "message": "No products scraped."}

    success_count = 0
    for product in scraped_data:
        try:
            response = requests.post(ENDPOINT_URL, json=product)
            if response.status_code == 200:
                success_count += 1
            else:
                print(f"Failed to post product: {response.text}")
        except Exception as e:
            print(f"Error posting product: {e}")

    return {
        "status": "success",
        "total_scraped": len(scraped_data),
        "successfully_uploaded": success_count
    }
