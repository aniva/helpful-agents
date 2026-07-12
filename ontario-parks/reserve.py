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
import argparse
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
            start_time = time.monotonic()
            input_str = ""
            while True:
                if time.monotonic() - start_time > timeout:
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
    print("\n[Telegram Config] Checking for updates to find your Telegram Chat ID...")
    print("Please open Telegram, find your bot, and send a message (e.g. '/start' or 'hi').")
    print("Waiting for your message...")
    
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    
    for attempt in range(20):
        try:
            res = requests.get(url, timeout=10)
            if res.status_code == 200:
                updates = res.json().get("result", [])
                if updates:
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

def check_gmail_confirmation(email_user, app_password, date_str):
    print(f"\nConnecting to Gmail ({email_user}) via IMAP to check for reservation confirmation email...")
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(email_user, app_password)
        mail.select("inbox")
        
        status, messages = mail.search(None, '(SUBJECT "Ontario Parks")')
        if status != "OK":
            print("Failed to search emails.")
            return None
            
        mail_ids = messages[0].split()
        if not mail_ids:
            print("No matching Ontario Parks emails found.")
            return None
            
        latest_id = mail_ids[-1]
        status, data = mail.fetch(latest_id, "(RFC822)")
        if status != "OK":
            return None
            
        raw_email = data[0][1]
        msg = email.message_from_bytes(raw_email)
        
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
        
        if "Confirmation" in text_content or "Reservation" in text_content or "OP-" in text_content:
            print("Found confirmation keywords in the email body!")
            debug_path = os.path.join(os.path.dirname(__file__), "confirmation_email.txt")
            with open(debug_path, "w", encoding="utf-8") as f:
                f.write(text_content)
            return text_content
            
        return None
    except Exception as e:
        print(f"Error checking email: {e}")
        return None

def login_to_ontario_parks(page, email_user, password):
    print("Navigating to sign in page...")
    page.goto("https://reservations.ontarioparks.ca/sign-in", timeout=40000)
    page.wait_for_load_state("networkidle")
    time.sleep(2)
    
    email_input = page.locator("input[type='email'], input[id*='email'], input[formcontrolname='email']")
    if email_input.count() > 0 and email_input.first.is_visible():
        print(f"Signing in as {email_user}...")
        email_input.first.fill(email_user)
        time.sleep(1)
        
        password_input = page.locator("input[type='password'], input[id*='password'], input[formcontrolname='password']")
        if password_input.count() > 0:
            password_input.first.fill(password)
            time.sleep(1)
            
        sign_in_btn = page.locator("button:has-text('Sign in'), button:has-text('Sign In')")
        if sign_in_btn.count() > 0:
            sign_in_btn.first.click()
            print("Submitted credentials, waiting for navigation...")
            time.sleep(5)
            page.wait_for_load_state("networkidle")
    else:
        print("Already signed in or credentials form not found.")

def run_checkout_wizard(page, config):
    """
    Scans and automates the sequential checkout wizard panels headlessly.
    """
    print("\nStarting automated checkout wizard...")
    for attempt in range(25):
        # 1. Review Reservation Details checkbox + confirm (Screenshot 3)
        review_chk = page.locator("mat-checkbox:has-text('details are correct'), mat-checkbox")
        review_btn = page.locator("button:has-text('Confirm reservation details')")
        if review_btn.count() > 0 and review_btn.first.is_visible():
            print("Wizard: Confirming reservation details...")
            if review_chk.count() > 0 and not review_chk.first.is_checked():
                review_chk.first.click()
                time.sleep(1)
            review_btn.first.click()
            time.sleep(3)
            page.wait_for_load_state("networkidle")
            continue
            
        # 2. Shopping Cart proceed (Screenshot 4)
        cart_btn = page.locator("button:has-text('Proceed to checkout')")
        if cart_btn.count() > 0 and cart_btn.first.is_visible():
            print("Wizard: Proceeding to checkout from shopping cart...")
            cart_btn.first.click()
            time.sleep(3)
            page.wait_for_load_state("networkidle")
            continue
            
        # 3. Policies Checkbox & Acknowledgement (Screenshot 6)
        policies_chk = page.locator("mat-checkbox:has-text('agree'), mat-checkbox")
        policies_btn = page.locator("button:has-text('Confirm acknowledgements')")
        if policies_btn.count() > 0 and policies_btn.first.is_visible():
            print("Wizard: Confirming policies acknowledgements...")
            if policies_chk.count() > 0 and not policies_chk.first.is_checked():
                policies_chk.first.click()
                time.sleep(1)
            policies_btn.first.click()
            time.sleep(3)
            page.wait_for_load_state("networkidle")
            continue
            
        # 4. Confirm Account Info (Screenshot 7)
        acc_btn = page.locator("button:has-text('Confirm account details')")
        if acc_btn.count() > 0 and acc_btn.first.is_visible():
            print("Wizard: Confirming account details...")
            acc_btn.first.click()
            time.sleep(3)
            page.wait_for_load_state("networkidle")
            continue
            
        # 5. Occupant details (Screenshot 8)
        occupant_radio = page.locator("text=I will be the occupant")
        occupant_btn = page.locator("button:has-text('Confirm occupant')")
        if occupant_btn.count() > 0 and occupant_btn.first.is_visible():
            print("Wizard: Selecting occupant...")
            if occupant_radio.count() > 0:
                occupant_radio.first.click()
                time.sleep(1)
            occupant_btn.first.click()
            time.sleep(3)
            page.wait_for_load_state("networkidle")
            continue
            
        # 6. Additional Info details - Plate & Seasonal Permit (Screenshot 9)
        additional_btn = page.locator("button:has-text('Confirm additional information')")
        if additional_btn.count() > 0 and additional_btn.first.is_visible():
            print("Wizard: Auto-filling plate and permit info...")
            seasonal_radio = page.locator("text=Seasonal Vehicle Permit Holder")
            if seasonal_radio.count() > 0:
                seasonal_radio.first.click()
                time.sleep(1)
                
            permit_input = page.locator("input[placeholder*='Pass'], input[id*='pass'], input[formcontrolname*='pass'], input[id*='Pass']")
            if permit_input.count() > 0:
                permit_input.first.fill(config["permit_number"])
                print(" - Filled permit number:", config["permit_number"])
                time.sleep(0.5)
                
            plate_input = page.locator("input[placeholder*='Plate'], input[id*='plate'], input[formcontrolname*='plate'], input[formcontrolname*='LicensePlate']")
            if plate_input.count() > 0:
                plate_input.first.fill(config["vehicle_plate"])
                print(" - Filled license plate:", config["vehicle_plate"])
                time.sleep(0.5)
                
            province_input = page.locator("input[placeholder*='Province'], input[id*='province'], input[formcontrolname*='province'], input[formcontrolname*='Province']")
            if province_input.count() > 0:
                province_input.first.fill(config["vehicle_province"])
                print(" - Filled province:", config["vehicle_province"])
                time.sleep(0.5)
                
            additional_btn.first.click()
            time.sleep(3)
            page.wait_for_load_state("networkidle")
            continue
            
        # 7. Final Confirmation (Screenshot 10)
        confirm_btn = page.locator("button:has-text('Confirm booking')")
        if confirm_btn.count() > 0 and confirm_btn.first.is_visible():
            print("Wizard: Finalizing and clicking Confirm Booking...")
            confirm_btn.first.click()
            time.sleep(5)
            page.wait_for_load_state("networkidle")
            continue
            
        # 8. Success page checking (Screenshot 11)
        if "Success!" in page.locator("body").inner_text() or page.locator("text=Success!").count() > 0:
            print("Wizard complete: Success page reached!")
            break
            
        time.sleep(2)

def list_reservations(email_user, password, headless=True):
    print("Launching browser to list reservations...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()
        
        login_to_ontario_parks(page, email_user, password)
        
        print("Navigating to My Reservations...")
        page.goto("https://reservations.ontarioparks.ca/account/all-bookings", timeout=40000)
        page.wait_for_load_state("networkidle")
        time.sleep(3)
        
        page_text = page.locator("body").inner_text()
        
        import re
        reservations = []
        blocks = page_text.split("Reservation No")
        for block in blocks[1:]:
            num_match = re.search(r"(?::|#)?\s*([A-Z0-9\-]+)", block)
            res_num = num_match.group(1).strip() if num_match else "Unknown"
            
            park_match = re.search(r"([A-Za-z\s']+\s*Provincial\s*Park)", block)
            park = park_match.group(1).strip() if park_match else "Unknown"
            
            date_match = re.search(r"([A-Z][a-z]{2},\s*[A-Z][a-z]{2}\s*\d{1,2},\s*\d{4})", block)
            res_date = date_match.group(1).strip() if date_match else "Unknown"
            
            occ_match = re.search(r"Occupant\s*:?\s*([A-Za-z\s]+)", block, re.IGNORECASE)
            occupant = occ_match.group(1).strip().split("\n")[0] if occ_match else "Unknown"
            
            veh_match = re.search(r"Vehicle\s*:?\s*([A-Z0-9]+)", block, re.IGNORECASE)
            vehicle = veh_match.group(1).strip() if veh_match else "Unknown"
            
            reservations.append({
                "reservation_number": res_num,
                "park": park,
                "date": res_date,
                "occupant": occupant,
                "vehicle": vehicle
            })
            
        # Write to JSON file
        out_path = os.path.join(os.path.dirname(__file__), "active_reservations.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(reservations, f, indent=2)
            
        print(f"List results saved to {out_path}")
        browser.close()
        return reservations

def cancel_reservation(email_user, password, target_res_num, headless=True):
    print(f"Launching browser to cancel reservation {target_res_num}...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()
        
        login_to_ontario_parks(page, email_user, password)
        
        print("Navigating to My Reservations...")
        page.goto("https://reservations.ontarioparks.ca/account/all-bookings", timeout=40000)
        page.wait_for_load_state("networkidle")
        time.sleep(3)
        
        # Locate card containing the target reservation number
        card = page.locator("div, section, mat-card", has_text=target_res_num)
        
        cancel_btn = card.locator("button:has-text('Cancel reservation')")
        if cancel_btn.count() > 0 and cancel_btn.first.is_visible():
            print("Found Cancel button! Clicking it...")
            cancel_btn.first.click()
            time.sleep(4)
            page.wait_for_load_state("networkidle")
            
            confirm_cancel_btn = page.locator("button:has-text('Cancel reservation'), button:has-text('Confirm')")
            if confirm_cancel_btn.count() > 0:
                print("Confirming cancellation...")
                confirm_cancel_btn.first.click()
                time.sleep(5)
                print(f"Reservation {target_res_num} cancelled successfully!")
                browser.close()
                return True
        else:
            print(f"Error: Could not find active 'Cancel reservation' button for {target_res_num}.")
            
        browser.close()
        return False

def main():
    config = load_config()
    
    parser = argparse.ArgumentParser(description="Ontario Parks Reservation Helper")
    subparsers = parser.add_subparsers(dest="command")
    
    # Subcommands
    book_parser = subparsers.add_parser("book", help="Book a daily vehicle permit")
    book_parser.add_argument("--park", help="Name of the park (e.g. 'Sibbald Point')")
    book_parser.add_argument("--date", help="Date: 'today', 'tomorrow', 'day_after', or YYYY-MM-DD")
    book_parser.add_argument("--headless", type=str, choices=["true", "false"], default="true", help="Run headlessly")
    
    list_parser = subparsers.add_parser("list", help="List active reservations")
    list_parser.add_argument("--headless", type=str, choices=["true", "false"], default="true")
    
    cancel_parser = subparsers.add_parser("cancel", help="Cancel a reservation")
    cancel_parser.add_argument("--reservation", required=True, help="Reservation number (e.g. INOP26-XXXXXX)")
    cancel_parser.add_argument("--headless", type=str, choices=["true", "false"], default="true")
    
    # Flags (for backward compatibility)
    parser.add_argument("--setup-telegram", action="store_true", help="Configure Telegram Chat ID")
    parser.add_argument("--forecast-only", action="store_true", help="Only show wind forecast and exit")
    
    args = parser.parse_args()
    
    # 1. Handle Setup commands
    if args.setup_telegram or (len(sys.argv) > 1 and sys.argv[1] == "--setup-telegram"):
        chat_id = resolve_telegram_chat_id(config["telegram_token"])
        if chat_id:
            config["telegram_chat_id"] = chat_id
            save_config(config)
            send_telegram_message(config["telegram_token"], chat_id, "⚙️ Telegram integration successfully verified!")
            print("Telegram Chat ID updated and test message sent successfully.")
        sys.exit(0)
        
    # 2. Handle subcommands
    if args.command == "list":
        password = config.get("ontario_parks_password")
        if not password:
            print("Error: 'ontario_parks_password' is not configured in ontario_parks_config.json!")
            sys.exit(1)
        headless = args.headless == "true"
        reservations = list_reservations(config["email"], password, headless=headless)
        print("\nActive Reservations List:")
        print("=" * 80)
        for r in reservations:
            print(f"Num: {r['reservation_number']:<18} | Park: {r['park']:<28} | Date: {r['date']:<16} | Vehicle: {r['vehicle']}")
        print("=" * 80)
        sys.exit(0)
        
    elif args.command == "cancel":
        password = config.get("ontario_parks_password")
        if not password:
            print("Error: 'ontario_parks_password' is not configured in ontario_parks_config.json!")
            sys.exit(1)
        headless = args.headless == "true"
        success = cancel_reservation(config["email"], password, args.reservation, headless=headless)
        if success:
            sys.exit(0)
        else:
            sys.exit(1)
            
    # Default to booking flow
    is_headless = True
    target_park_override = None
    target_date_override = None
    
    if args.command == "book":
        is_headless = args.headless == "true"
        target_park_override = args.park
        target_date_override = args.date
        
    # Ask about date if not overridden
    today = datetime.date.today()
    dates = [
        ("Today", today),
        ("Tomorrow", today + datetime.timedelta(days=1)),
        ("Day after tomorrow", today + datetime.timedelta(days=2))
    ]
    
    if target_date_override:
        if target_date_override.lower() == "today":
            choice = 1
        elif target_date_override.lower() == "tomorrow":
            choice = 2
        elif target_date_override.lower() == "day_after":
            choice = 3
        else:
            try:
                custom_date = datetime.datetime.strptime(target_date_override, "%Y-%m-%d").date()
                dates = [("Custom Date", custom_date)]
                choice = 1
            except ValueError:
                print(f"Error: Invalid date format '{target_date_override}'. Use YYYY-MM-DD, today, tomorrow, or day_after.")
                sys.exit(1)
    else:
        print("=" * 60)
        print("Ontario Park Daily Vehicle Permit Helper")
        print("=" * 60)
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
    
    if args.forecast_only:
        print("\n[Weather/Wind] Fetching wind forecasts for participating kiting parks...")
        for name, info in PARKS.items():
            forecast = fetch_weather_forecast(info["lat"], info["lon"], target_date_str)
            if forecast:
                print(f" - {name:<30} | Wind: {forecast['max_speed']:>4} kts (Gust: {forecast['max_gust']:>4} kts) | {forecast['condition']}")
        sys.exit(0)
        
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
            
    ranked_parks.sort(key=lambda x: x["max_speed"], reverse=True)
    
    print("\n" + "="*70)
    print(f"Kiting Parks Forecast for {target_date.strftime('%A, %b %d')} (Sorted by Max Wind)")
    print("="*70)
    
    prev_selected = config.get("previously_selected_park", "")
    for idx, p in enumerate(ranked_parks):
        marker = "⭐ [PREV SELECT]" if p["name"] == prev_selected else ""
        print(f" {idx + 1}. {p['name']:<30} | Max Wind: {p['max_speed']:>4} kts (Gust: {p['max_gust']:>4} kts) | Dir: {p['dir']:<3} | {p['condition']:<15} {marker}")
    print("="*70)
    
    selected_park = None
    if target_park_override:
        for p in ranked_parks:
            if target_park_override.lower() in p["name"].lower():
                selected_park = p
                break
        if not selected_park:
            print(f"Error: Overridden park name '{target_park_override}' could not be matched!")
            sys.exit(1)
    else:
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
    
    config["previously_selected_park"] = park_name
    save_config(config)
    
    print(f"\nProceeding to book {park_name} for {target_date_str}.")
    
    print("\nLaunching browser to automate reservations.ontarioparks.ca...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=is_headless)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()
        
        print("Navigating to homepage...")
        page.goto("https://reservations.ontarioparks.ca/", timeout=40000)
        page.wait_for_load_state("networkidle")
        
        print("Opening Day Use section...")
        page.click("#mat-tab-link-1")
        time.sleep(1)
        
        print(f"Searching for park: '{park_search_name}'...")
        page.fill("#park-autocomplete-input", park_search_name)
        time.sleep(2)
        page.press("#park-autocomplete-input", "ArrowDown")
        time.sleep(1)
        page.press("#park-autocomplete-input", "Enter")
        time.sleep(1)
        
        print("Selecting date in calendar...")
        page.click("#arrival-date-field")
        time.sleep(2)
        date_label = f"{target_date.strftime('%B')} {target_date.day}, {target_date.year}"
        page.click(f"[aria-label='{date_label}']")
        time.sleep(1)
        
        print("Submitting search...")
        page.click("#actionSearch")
        time.sleep(5)
        
        consent_btn = page.locator("#consentButton")
        if consent_btn.count() > 0 and consent_btn.is_visible():
            print("Accepting rules consent...")
            consent_btn.click()
            time.sleep(2)
            
        print("Locating available slot cell...")
        headers = page.locator("table.chart tr").first.locator("td, th").all()
        target_col_text = target_date.strftime("%b %d")
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
        
        print("Clicking Reserve...")
        page.click("#reserveButton")
        time.sleep(4)
        page.wait_for_load_state("networkidle")
        
        password = config.get("ontario_parks_password")
        if is_headless and not password:
            print("Error: Headless run selected, but 'ontario_parks_password' is not configured!")
            browser.close()
            sys.exit(1)
            
        if password:
            login_to_ontario_parks(page, config["email"], password)
        else:
            print("\n" + "*"*80)
            print("⚠️ ACTION REQUIRED: If you are not signed in, please log in to your Ontario Parks")
            print("account now in the opened browser window.")
            print("Once you are signed in and see the checkout wizard or additional info page, press Enter here.")
            print("*"*80)
            input_with_timeout("\nPress Enter to continue after logging in (Timeout in 180s)...", timeout=180, default="")
            
        run_checkout_wizard(page, config)
        
        print("Wizard Completed. Running preregistration automation...")
        try:
            preregister_btn = page.locator("button:has-text('Preregister'), a:has-text('Preregister')")
            if preregister_btn.count() > 0 and preregister_btn.first.is_visible():
                preregister_btn.first.click()
                time.sleep(4)
                page.wait_for_load_state("networkidle")
                
                preregister_now_btn = page.locator("button:has-text('Preregister now')")
                if preregister_now_btn.count() > 0 and preregister_now_btn.first.is_visible():
                    preregister_now_btn.first.click()
                    time.sleep(4)
                    page.wait_for_load_state("networkidle")
                    print("Successfully Preregistered vehicle plate!")
        except Exception as e:
            print("Warning: Preregistration failed with issue:", e)
            
        print("\nScanning page for reservation number...")
        conf_number = "Unknown"
        page_text = page.locator("body").inner_text()
        
        import re
        match = re.search(r"INOP\d+-\d+|INOP\d+-[A-Z0-9]+|OP-\d+", page_text)
        if match:
            conf_number = match.group(0)
            print(f"Captured confirmation number: {conf_number}")
        else:
            match_any = re.search(r"Reservation\s*(?:Number|#)?\s*:?\s*([A-Z0-9\-]+)", page_text, re.IGNORECASE)
            if match_any:
                conf_number = match_any.group(1).strip()
                print(f"Captured confirmation number: {conf_number}")
                
        screenshot_name = f"confirmation_{target_date_str}_{conf_number.replace('-', '_')}.png"
        screenshot_path = os.path.join(os.path.dirname(__file__), screenshot_name)
        page.screenshot(path=screenshot_path)
        print(f"Saved confirmation screenshot to {screenshot_path}")
        
        browser.close()
        
    email_verified = "No (skipped or not found)"
    if config.get("gmail_app_password"):
        print("\nWaiting 15 seconds for Ontario Parks to send email receipt...")
        time.sleep(15)
        email_body = check_gmail_confirmation(config["email"], config["gmail_app_password"], target_date_str)
        if email_body:
            email_verified = "Yes"
            
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
