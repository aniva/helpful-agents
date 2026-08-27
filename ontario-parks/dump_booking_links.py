import time
import os
import sys
from playwright.sync_api import sync_playwright

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from reserve import load_config

config = load_config()
email = config["email"]
password = os.environ.get("ONTARIO_PARKS_PASSWORD", config.get("ontario_parks_password", ""))

print(f"Credentials loaded: email={email}, password_len={len(password) if password else 0}")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    context = browser.new_context(
        user_agent=user_agent,
        viewport={"width": 1280, "height": 800},
        extra_http_headers={"Accept-Language": "en-US,en;q=0.9"}
    )
    page = context.new_page()
    page.add_init_script("delete navigator.__proto__.webdriver;")
    
    print("Navigating to home...")
    page.goto("https://reservations.ontarioparks.ca/", timeout=45000)
    time.sleep(3)
    
    consent_btn = page.locator("button:has-text('I consent'), button:has-text('I Consent')")
    if consent_btn.count() > 0:
        consent_btn.first.click()
        time.sleep(1.5)
        
    print("Navigating to login...")
    page.goto("https://reservations.ontarioparks.ca/login", timeout=45000)
    time.sleep(3)
    
    consent_btn = page.locator("button:has-text('I consent'), button:has-text('I Consent')")
    if consent_btn.count() > 0:
        consent_btn.first.click()
        time.sleep(1.5)
        
    print("Logging in...")
    page.locator("input#email").first.fill(email)
    page.locator("input#password").first.fill(password)
    page.locator("#loginButton").first.click()
    
    time.sleep(6)
    
    print("Navigating to My Reservations...")
    page.goto("https://reservations.ontarioparks.ca/account/all-bookings", timeout=45000)
    time.sleep(6)
    
    # Let's find all links (hrefs) on the page
    links = page.locator("a").all()
    print(f"Found {len(links)} links on the page:")
    for a in links:
        href = a.get_attribute("href")
        text = a.inner_text().strip().replace("\n", " ")
        if href:
            print(f"- Link: href={href}, text='{text}'")
            
    browser.close()
