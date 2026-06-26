import os
import sys
import json
import time
import datetime
import imaplib
import email
from email.header import decode_header
import requests
import urllib3
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# Disable SSL warnings for the weather API
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Set console output encoding to UTF-8 to prevent UnicodeEncodeError on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "ontario_parks_config.json")

PARKS = {
    "Presqu'ile Provincial Park": {
        "search_name": "Presqu'ile",
        "lat": 43.9983,
        "lon": -77.7247
    },
    "Sandbanks Provincial Park": {
        "search_name": "Sandbanks",
        "lat": 43.9048,
        "lon": -77.2514
    },
    "Wasaga Beach Provincial Park": {
        "search_name": "Wasaga Beach",
        "lat": 44.4789,
        "lon": -80.0163
    },
    "Long Point Provincial Park": {
        "search_name": "Long Point",
        "lat": 42.5764,
        "lon": -80.3794
    },
    "Turkey Point Provincial Park": {
        "search_name": "Turkey Point",
        "lat": 42.7092,
        "lon": -80.3292
    },
    "Sibbald Point Provincial Park": {
        "search_name": "Sibbald Point",
        "lat": 44.3364,
        "lon": -79.3248
    },
    "Craigleith Provincial Park": {
        "search_name": "Craigleith",
        "lat": 44.5369,
        "lon": -80.2989
    }
}

WEATHER_CODES = {
    0: "Sunny/Clear",
    1: "Mainly Clear",
    2: "Partly Cloudy",
    3: "Overcast",
    45: "Foggy",
    48: "Depositing Rime Fog",
    51: "Light Drizzle",
    53: "Moderate Drizzle",
    55: "Dense Drizzle",
    61: "Slight Rain",
    63: "Moderate Rain",
    65: "Heavy Rain",
    71: "Slight Snow",
    73: "Moderate Snow",
    75: "Heavy Snow",
    77: "Snow Grains",
    80: "Slight Rain Showers",
    81: "Moderate Rain Showers",
    82: "Violent Rain Showers",
    85: "Slight Snow Showers",
    86: "Heavy Snow Showers",
    95: "Thunderstorm",
    96: "Thunderstorm with Slight Hail",
    99: "Thunderstorm with Heavy Hail"
}

def input_with_timeout(prompt, timeout=60, default=""):
    """
    Prompts the user for input and returns it.
    If no input is received within the specified timeout (in seconds) or if the terminal is non-interactive,
    returns the default value.
    """
    print(prompt, end="", flush=True)
    
    # If stdin is not a TTY, return default immediately to prevent hanging in background runners
    if not sys.stdin.isatty():
        print(f"\n[Non-Interactive] Auto-selecting default value: '{default}'")
        return default
        
    try:
        # Under Windows, use msvcrt to check for input without blocking
        if os.name == 'nt':
            import msvcrt
            start_time = time.time()
            input_str = ""
            while True:
                if time.time() - start_time > timeout:
                    print(f"\n[Timeout] Auto-selecting default value: '{default}'")
                    return default
                if msvcrt.kbhit():
                    char = msvcrt.getwche() # Reads character and echoes it
                    if char in ('\r', '\n'): # Enter key
                        print() # Move to next line
                        return input_str.strip()
                    elif char == '\b': # Backspace
                        if len(input_str) > 0:
                            input_str = input_str[:-1]
                            sys.stdout.write(' \b')
                            sys.stdout.flush()
                    else:
                        input_str += char
                time.sleep(0.05)
        else:
            # Under Linux/Unix/WSL, use select
            import select
            rlist, _, _ = select.select([sys.stdin], [], [], timeout)
            if rlist:
                return sys.stdin.readline().strip()
            else:
                print(f"\n[Timeout] Auto-selecting default value: '{default}'")
                return default
    except Exception as e:
        # Fallback if msvcrt or select fails
        print(f"\n[Error/Fallback] {e}. Auto-selecting default: '{default}'")
        return default

def load_config():
    if not os.path.exists(CONFIG_PATH):
        print(f"Error: Config file not found at {CONFIG_PATH}!")
        sys.exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_config(config):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

def get_compass_direction(degrees):
    val = int((degrees / 22.5) + .5)
    arr = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return arr[(val % 16)]

def fetch_weather_forecast(lat, lon, date_str):
    """
    Fetches hourly wind forecast for a specific park and date from Open-Meteo.
    Filters hours between 9:00 AM and 6:00 PM.
    """
    # Use wind_speed_unit=kn and verify=False to bypass SSL EOF issues on some networks
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=wind_speed_10m,wind_gusts_10m,wind_direction_10m,weather_code&wind_speed_unit=kn&timezone=America%2FNew_York"
    try:
        response = requests.get(url, timeout=10, verify=False)
        if response.status_code != 200:
            return None
        data = response.json()
        
        target_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        hourly = data.get("hourly", {})
        times = hourly.get("time", [])
        
        wind_speeds = []
        wind_gusts = []
        wind_dirs = []
        weather_codes = []
        
        for idx, t_str in enumerate(times):
            # Format: '2026-06-27T09:00'
            dt = datetime.datetime.fromisoformat(t_str)
            if dt.date() == target_date and 9 <= dt.hour <= 18:
                wind_speeds.append(hourly["wind_speed_10m"][idx])
                wind_gusts.append(hourly["wind_gusts_10m"][idx])
                wind_dirs.append(hourly["wind_direction_10m"][idx])
                weather_codes.append(hourly["weather_code"][idx])
                
        if not wind_speeds:
            return None
            
        avg_speed = sum(wind_speeds) / len(wind_speeds)
        max_speed = max(wind_speeds)
        max_gust = max(wind_gusts)
        avg_dir = sum(wind_dirs) / len(wind_dirs)
        # Find most common weather code
        code = max(set(weather_codes), key=weather_codes.count)
        
        return {
            "avg_speed": round(avg_speed, 1),
            "max_speed": round(max_speed, 1),
            "max_gust": round(max_gust, 1),
            "compass_dir": get_compass_direction(avg_dir),
            "condition": WEATHER_CODES.get(code, "Unknown")
        }
    except Exception as e:
        print(f"Error fetching forecast: {e}")
        return None

def resolve_telegram_chat_id(token):
    """
    Checks recent updates from Telegram Bot API to find the user's Chat ID.
    """
    print("\n[Telegram Config] Checking for updates to find your Telegram Chat ID...")
    print("Please open Telegram, find your bot, and send a message (e.g. '/start' or 'hi').")
    print("Waiting for your message...")
    
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    
    # Poll for 60 seconds
    for attempt in range(20):
        try:
            res = requests.get(url, timeout=10)
            if res.status_code == 200:
                updates = res.json().get("result", [])
                if updates:
                    # Look for the last update containing message details
                    for update in reversed(updates):
                        msg = update.get("message")
                        if msg:
                            chat_id = msg["chat"]["id"]
                            chat_user = msg["chat"].get("username", "")
                            print(f"\n[Telegram Config] Found message from @{chat_user} (Chat ID: {chat_id})!")
                            return str(chat_id)
            time.sleep(3)
            print(".", end="", flush=True)
        except Exception as e:
            print(f"\nError: {e}")
            break
            
    print("\n[Telegram Config] Timeout: Could not find any recent messages. Please try again.")
    return None

def send_telegram_message(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        return res.status_code == 200
    except Exception as e:
        print(f"Error sending message: {e}")
        return False

def check_gmail_confirmation(email_user, app_password, date_str, expected_conf_num=None):
    """
    Connects to Gmail IMAP, searches for recent Ontario Parks confirmation emails,
    and returns reservation details if found.
    """
    print(f"\nConnecting to Gmail ({email_user}) via IMAP to check for reservation confirmation email...")
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(email_user, app_password)
        mail.select("inbox")
        
        # Search for messages from ontarioparks.ca or containing "Ontario Parks" in subject
        status, messages = mail.search(None, '(SUBJECT "Ontario Parks")')
        if status != "OK":
            print("Failed to search emails.")
            return None
            
        mail_ids = messages[0].split()
        if not mail_ids:
            print("No matching Ontario Parks emails found.")
            return None
            
        # Get the most recent email
        latest_id = mail_ids[-1]
        status, data = mail.fetch(latest_id, "(RFC822)")
        if status != "OK":
            return None
            
        raw_email = data[0][1]
        msg = email.message_from_bytes(raw_email)
        
        # Decode Subject
        subject, encoding = decode_header(msg["Subject"])[0]
        if isinstance(subject, bytes):
            subject = subject.decode(encoding or "utf-8")
            
        print(f"Latest email subject: '{subject}'")
        
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))
                if content_type == "text/plain" and "attachment" not in content_disposition:
                    body = part.get_payload(decode=True).decode()
                    break
        else:
            body = msg.get_payload(decode=True).decode()
            
        soup = BeautifulSoup(body, "html.parser")
        text_content = soup.get_text()
        
        # Search for reservation number or confirmation details
        if "Confirmation" in text_content or "Reservation" in text_content or "OP-" in text_content:
            print("Found confirmation keywords in the email body!")
            # Save email content to debug file
            debug_path = os.path.join(os.path.dirname(__file__), "confirmation_email.txt")
            with open(debug_path, "w", encoding="utf-8") as f:
                f.write(text_content)
            return text_content
            
        return None
    except Exception as e:
        print(f"Error checking email: {e}")
        return None

def main():
    config = load_config()
    
    # 1. Ask about date
    print("=" * 60)
    print("Ontario Park Daily Vehicle Permit Helper")
    print("=" * 60)
    
    today = datetime.date.today()
    dates = [
        ("Today", today),
        ("Tomorrow", today + datetime.timedelta(days=1)),
        ("Day after tomorrow", today + datetime.timedelta(days=2))
    ]
    
    print("\nSelect a reservation date:")
    for idx, (label, d) in enumerate(dates):
        print(f" {idx + 1}. {label} ({d.strftime('%A, %b %d, %Y')})")
        
    choice = input_with_timeout("\nEnter date selection (1-3) [default: 2 (Tomorrow)]: ", timeout=30, default="2").strip()
    if not choice:
        choice = 2
    else:
        try:
            choice = int(choice)
            if choice < 1 or choice > 3:
                choice = 2
        except ValueError:
            choice = 2
            
    target_label, target_date = dates[choice - 1]
    target_date_str = target_date.strftime("%Y-%m-%d")
    print(f"\nSelected Date: {target_label} ({target_date_str})")
    
    # Check if CLI argument is given to configure Telegram
    if len(sys.argv) > 1 and sys.argv[1] == "--setup-telegram":
        chat_id = resolve_telegram_chat_id(config["telegram_token"])
        if chat_id:
            config["telegram_chat_id"] = chat_id
            save_config(config)
            send_telegram_message(config["telegram_token"], chat_id, "⚙️ Telegram integration successfully verified!")
            print("Telegram Chat ID updated and test message sent successfully.")
        sys.exit(0)
        
    # Check if we need to resolve Chat ID
    if not config.get("telegram_chat_id"):
        print("\n⚠️ Telegram Chat ID is not configured!")
        setup = input_with_timeout("Would you like to resolve your Telegram Chat ID now? (y/n) [default: y]: ", timeout=30, default="y").strip().lower()
        if not setup or setup == 'y':
            chat_id = resolve_telegram_chat_id(config["telegram_token"])
            if chat_id:
                config["telegram_chat_id"] = chat_id
                save_config(config)
                send_telegram_message(config["telegram_token"], chat_id, "⚙️ Telegram integration successfully verified!")
            else:
                print("Could not resolve Chat ID. Notifications will fail. You can configure it manually in config.json.")
                
    # 2. Weather & Wind Forecast fetching and ranking
    print("\n[Weather/Wind] Fetching wind forecasts for participating kiting parks...")
    ranked_parks = []
    for name, info in PARKS.items():
        forecast = fetch_weather_forecast(info["lat"], info["lon"], target_date_str)
        if forecast:
            ranked_parks.append({
                "name": name,
                "max_speed": forecast["max_speed"],
                "avg_speed": forecast["avg_speed"],
                "max_gust": forecast["max_gust"],
                "dir": forecast["compass_dir"],
                "condition": forecast["condition"]
            })
            
    # Sort by maximum wind speed descending
    ranked_parks.sort(key=lambda x: x["max_speed"], reverse=True)
    
    print("\n" + "="*70)
    print(f"Kiting Parks Forecast for {target_date.strftime('%A, %b %d')} (Sorted by Max Wind)")
    print("="*70)
    
    prev_selected = config.get("previously_selected_park", "")
    for idx, p in enumerate(ranked_parks):
        marker = "⭐ [PREV SELECT]" if p["name"] == prev_selected else ""
        print(f" {idx + 1}. {p['name']:<30} | Max Wind: {p['max_speed']:>4} kts (Gust: {p['max_gust']:>4} kts) | Dir: {p['dir']:<3} | {p['condition']:<15} {marker}")
    print("="*70)
    
    # 3. Select park
    park_choice = input_with_timeout(f"\nSelect a park to reserve (1-{len(ranked_parks)}) [default: 1]: ", timeout=45, default="1").strip()
    if not park_choice:
        park_choice = 1
    else:
        try:
            park_choice = int(park_choice)
            if park_choice < 1 or park_choice > len(ranked_parks):
                park_choice = 1
        except ValueError:
            park_choice = 1
            
    selected_park = ranked_parks[park_choice - 1]
    park_name = selected_park["name"]
    park_search_name = PARKS[park_name]["search_name"]
    
    # Update config previously selected park
    config["previously_selected_park"] = park_name
    save_config(config)
    
    print(f"\nProceeding to book {park_name} for {target_date_str}.")
    
    # 4. Playwright Automation
    print("\nLaunching browser to automate reservations.ontarioparks.ca...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()
        
        print("Navigating to homepage...")
        page.goto("https://reservations.ontarioparks.ca/", timeout=40000)
        page.wait_for_load_state("networkidle")
        
        # Click on Day Use tab link
        print("Opening Day Use section...")
        page.click("#mat-tab-link-1")
        time.sleep(1)
        
        # Fill in the park
        print(f"Searching for park: '{park_search_name}'...")
        page.fill("#park-autocomplete-input", park_search_name)
        time.sleep(2)
        page.press("#park-autocomplete-input", "ArrowDown")
        time.sleep(1)
        page.press("#park-autocomplete-input", "Enter")
        time.sleep(1)
        
        # Select Date
        print("Selecting date in calendar...")
        page.click("#arrival-date-field")
        time.sleep(2)
        # Format label: 'June 27, 2026'
        date_label = f"{target_date.strftime('%B')} {target_date.day}, {target_date.year}"
        page.click(f"[aria-label='{date_label}']")
        time.sleep(1)
        
        # Search
        print("Submitting search...")
        page.click("#actionSearch")
        time.sleep(5)
        
        # Consent modal check
        consent_btn = page.locator("#consentButton")
        if consent_btn.count() > 0 and consent_btn.is_visible():
            print("Accepting rules consent...")
            consent_btn.click()
            time.sleep(2)
            
        # Grid Cell Selection
        # Row 0 cells contain target date short name (e.g. 'Jun 27')
        print("Locating available slot cell...")
        headers = page.locator("table.chart tr").first.locator("td, th").all()
        target_col_text = target_date.strftime("%b %d") # e.g. 'Jun 27'
        col_index = -1
        for idx, h in enumerate(headers):
            text = h.inner_text().strip()
            if target_col_text in text:
                col_index = idx
                break
                
        if col_index == -1:
            print(f"Error: Target column '{target_col_text}' not found in availability grid!")
            browser.close()
            sys.exit(1)
            
        row_cells = page.locator("table.chart tr").nth(1).locator("td, th").all()
        cell = row_cells[col_index]
        label = cell.get_attribute("aria-label") or ""
        
        if "Available" not in label:
            print(f"Error: Daily Vehicle Permit for {park_name} on {target_date_str} is NOT available!")
            print(f"Current cell label: '{label}'")
            browser.close()
            sys.exit(1)
            
        print("Permit is available! Selecting day slot...")
        cell.click()
        time.sleep(2)
        
        # Click Reserve Button
        print("Clicking Reserve...")
        page.click("#reserveButton")
        time.sleep(4)
        
        # Login prompt
        print("\n" + "*"*80)
        print("⚠️ ACTION REQUIRED: If you are not signed in, please log in to your Ontario Parks")
        print("account now in the opened browser window.")
        print("Once you are signed in and see the 'Additional Information' page, press Enter here.")
        print("*"*80)
        input_with_timeout("\nPress Enter to continue after logging in (Timeout in 180s)...", timeout=180, default="")
        
        # Now fill in vehicle and permit details
        print("\nFilling Additional Information fields...")
        try:
            # 1. Choose Seasonal Vehicle Permit Holder option
            # Look for radio button containing the text
            page.locator("text=Seasonal Vehicle Permit Holder").first.click()
            time.sleep(1)
            
            # 2. Enter permit number S-2632347
            # Locator: search input next to label, or with formcontrolname
            permit_input = page.locator("input[placeholder*='Pass'], input[id*='pass'], input[formcontrolname*='pass'], input[id*='Pass']")
            if permit_input.count() > 0:
                permit_input.first.fill(config["permit_number"])
                print(" - Filled permit number:", config["permit_number"])
            
            # 3. Enter License Plate
            plate_input = page.locator("input[placeholder*='Plate'], input[id*='plate'], input[formcontrolname*='plate'], input[formcontrolname*='LicensePlate']")
            if plate_input.count() > 0:
                plate_input.first.fill(config["vehicle_plate"])
                print(" - Filled license plate:", config["vehicle_plate"])
                
            # 4. Enter Province
            province_input = page.locator("input[placeholder*='Province'], input[id*='province'], input[formcontrolname*='province'], input[formcontrolname*='Province']")
            if province_input.count() > 0:
                # If it's a input field
                province_input.first.fill(config["vehicle_province"])
                print(" - Filled province:", config["vehicle_province"])
            
            # Let's wait a second to make sure inputs are registered
            time.sleep(1)
            
            # Click green Confirm Additional Information button
            # Class: .raised-btn, .mat-primary, or text contains 'Confirm'
            confirm_btn = page.locator("button:has-text('Confirm additional information'), button:has-text('Confirm')")
            if confirm_btn.count() > 0:
                print("Clicking confirm button...")
                confirm_btn.first.click()
                time.sleep(3)
        except Exception as e:
            print("Warning: Automation autofill encountered an issue:", e)
            print("Please fill in the details manually in the browser, then continue.")
            
        print("\n" + "*"*80)
        print("⚠️ ACTION REQUIRED: Please review the final page in the browser (cart charge should be $0.00).")
        print("Click 'Checkout' / 'Confirm' button in the browser to complete the booking.")
        print("Once you see the reservation confirmation screen (with the Reservation Number), press Enter here.")
        print("*"*80)
        input_with_timeout("\nPress Enter to continue after checkout completion (Timeout in 180s)...", timeout=180, default="")
        
        # Capture confirmation number
        print("\nScanning page for reservation number...")
        conf_number = "Unknown"
        page_text = page.locator("body").inner_text()
        
        # Try to search for Reservation Number formats (e.g. OP-XXXXXX or numbers)
        import re
        match = re.search(r"OP-\d+", page_text)
        if match:
            conf_number = match.group(0)
            print(f"Captured confirmation number: {conf_number}")
        else:
            # Look for any pattern in URL or other places
            match_any = re.search(r"Reservation\s*(?:Number|#)?\s*:?\s*([A-Z0-9\-]+)", page_text, re.IGNORECASE)
            if match_any:
                conf_number = match_any.group(1).strip()
                print(f"Captured confirmation number: {conf_number}")
                
        # Take confirmation screenshot
        screenshot_name = f"confirmation_{target_date_str}_{conf_number.replace('-', '_')}.png"
        screenshot_path = os.path.join(os.path.dirname(__file__), screenshot_name)
        page.screenshot(path=screenshot_path)
        print(f"Saved confirmation screenshot to {screenshot_path}")
        
        browser.close()
        
    # 5. Gmail confirmation check
    email_verified = "No (skipped or not found)"
    if config.get("gmail_app_password"):
        print("\nWaiting 15 seconds for Ontario Parks to send email receipt...")
        time.sleep(15)
        email_body = check_gmail_confirmation(config["email"], config["gmail_app_password"], target_date_str)
        if email_body:
            email_verified = "Yes"
            
    # 6. Telegram notification
    msg_text = (
        f"🌊 <b>Ontario Park Reservation Confirmed!</b> 🌊\n\n"
        f"📍 <b>Park:</b> {park_name}\n"
        f"📅 <b>Date:</b> {target_label} ({target_date_str})\n"
        f"🚗 <b>Vehicle:</b> {config['vehicle_plate']} ({config['vehicle_province']})\n"
        f"🎫 <b>Permit:</b> {config['permit_number']}\n"
        f"🔑 <b>Confirmation #:</b> <code>{conf_number}</code>\n"
        f"📧 <b>Email verified:</b> {email_verified}\n\n"
        f"🌬️ <b>Wind Forecast:</b> Max {selected_park['max_speed']} kts (Gust: {selected_park['max_gust']} kts), Dir: {selected_park['dir']}, {selected_park['condition']}\n\n"
        f"Have a great kiting session! 🏄‍♂️💨"
    )
    
    if config.get("telegram_chat_id"):
        print("\nSending Telegram notification message...")
        success = send_telegram_message(config["telegram_token"], config["telegram_chat_id"], msg_text)
        if success:
            print("Telegram notification sent successfully!")
        else:
            print("Failed to send Telegram notification.")
    else:
        print("\nTelegram chat ID not configured, skipped notification.")
        print("Formatted message:")
        print(msg_text.replace("<b>", "").replace("</b>", "").replace("<code>", "").replace("</code>", ""))

if __name__ == "__main__":
    main()
