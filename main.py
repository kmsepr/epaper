import requests
import datetime
import os
from bs4 import BeautifulSoup

# Today's date
today = datetime.datetime.now().strftime("%Y-%m-%d")
edition = "Kozhikode"

# Step 1: Get the flipbook details page
def get_page_urls():
    base_url = f"https://epaper.suprabhaatham.com/details/{edition}/{today}/1"
    response = requests.get(base_url)
    if response.status_code != 200:
        raise Exception(f"Failed to access flipbook: {base_url}")

    soup = BeautifulSoup(response.text, 'html.parser')
    script_tag = soup.find("script", text=lambda t: t and "window.magazineData" in t)

    if not script_tag:
        raise Exception("Could not find page data script.")

    start = script_tag.string.find("window.magazineData = ") + len("window.magazineData = ")
    end = script_tag.string.find("};", start) + 1
    json_text = script_tag.string[start:end]

    import json
    data = json.loads(json_text)

    page_urls = [page["image"] for page in data["pages"]]
    return page_urls

# Step 2: Download all images
def download_pages(image_urls):
    folder = f"pages_{today}"
    os.makedirs(folder, exist_ok=True)

    for idx, url in enumerate(image_urls, start=1):
        response = requests.get(url)
        if response.status_code == 200:
            with open(f"{folder}/page_{idx}.jpg", "wb") as f:
                f.write(response.content)
                print(f"Downloaded page {idx}")
        else:
            print(f"Failed to download page {idx}: {url}")

if __name__ == "__main__":
    urls = get_page_urls()
    download_pages(urls)