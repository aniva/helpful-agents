import sys
import time
from playwright.sync_api import sync_playwright

def main():
    print("Launching browser in HEADLESS mode...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
        page = context.new_page()
        
        print("Navigating to reservations.ontarioparks.ca...")
        try:
            page.goto("https://reservations.ontarioparks.ca/", timeout=40000)
            page.wait_for_load_state("load")
            time.sleep(3)
            
            # Click Day Use tab
            page.click("#mat-tab-link-1")
            time.sleep(2)
            
            # Search Wasaga Beach
            print("Searching for Wasaga Beach...")
            page.fill("#park-autocomplete-input", "Wasaga Beach")
            time.sleep(2)
            page.press("#park-autocomplete-input", "ArrowDown")
            time.sleep(1)
            page.press("#park-autocomplete-input", "Enter")
            time.sleep(1)
            
            # Click actionSearch
            page.click("#actionSearch")
            print("Submitted search. Waiting 8 seconds...")
            time.sleep(8)
            
            # Capture screenshot
            page.screenshot(path="/home/me/ontario-parks/wasaga_search.png")
            print("Saved screenshot to wasaga_search.png")
            
            # Print page title and URL
            print("Title:", page.title())
            print("URL:", page.url)
            
        except Exception as e:
            print("Error occurred:", e)
        finally:
            browser.close()

if __name__ == "__main__":
    main()
