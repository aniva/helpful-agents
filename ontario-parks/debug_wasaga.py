from playwright.sync_api import sync_playwright
import time

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        print("Navigating to homepage...")
        page.goto("https://reservations.ontarioparks.ca/")
        page.wait_for_load_state("load")
        time.sleep(2)
        
        # Day Use
        day_use_tab = page.locator("#mat-tab-link-1, a:has-text('Day Use')")
        day_use_tab.first.click()
        time.sleep(1)
        
        # Fill Wasaga Beach
        print("Filling Wasaga Beach...")
        page.fill("#park-autocomplete-input", "Wasaga Beach")
        time.sleep(2)
        page.press("#park-autocomplete-input", "ArrowDown")
        time.sleep(1)
        page.press("#park-autocomplete-input", "Enter")
        time.sleep(1)
        
        # Select Wednesday Aug 19
        page.click("#arrival-date-field")
        time.sleep(2)
        page.click("[aria-label='August 19, 2026']")
        time.sleep(1)
        
        print("Submitting search...")
        page.click("#actionSearch")
        time.sleep(5)
        
        print("Page URL:", page.url)
        
        list_toggle = page.locator("#list-view-button-button")
        print("List toggle count:", list_toggle.count(), "is_visible:", list_toggle.is_visible() if list_toggle.count() > 0 else False)
        if list_toggle.count() > 0 and list_toggle.is_visible():
            list_toggle.click()
            time.sleep(3)
            page.screenshot(path="wasaga_list.png")
            
            options = page.locator("button.map-link-button, a.map-link-button").all()
            print(f"Found {len(options)} options matching button.map-link-button:")
            for opt in options:
                txt = (opt.text_content() or "").strip().replace("\n", " ")
                print(f"  - Option: '{txt}'")
                
            if not options:
                print("No map-link-button found! Listing all cards/buttons...")
                cards = page.locator(".resource-card, .location-card, button, a").all()
                for c in cards[:20]:
                    txt = (c.text_content() or "").strip().replace("\n", " ")
                    if txt and len(txt) < 150:
                        print(f"  - Element: '{txt}'")

        browser.close()

if __name__ == "__main__":
    main()
