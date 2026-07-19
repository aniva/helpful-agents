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

def load_env_file(filepath=None):
    if filepath is None:
        filepath = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ[key.strip()] = val.strip().strip("'\"")

def load_config():
    load_env_file()
    config = {}
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            try:
                config = json.load(f)
            except Exception:
                pass
                
    # Overlay with Environment Variables (with fallbacks to config JSON keys)
    config["email"] = os.environ.get("ONTARIO_PARKS_EMAIL", config.get("email", ""))
    config["ontario_parks_password"] = os.environ.get("ONTARIO_PARKS_PASSWORD", config.get("ontario_parks_password", ""))
    config["permit_number"] = os.environ.get("ONTARIO_PARKS_PERMIT", config.get("permit_number", ""))
    config["vehicle_plate"] = os.environ.get("ONTARIO_PARKS_PLATE", config.get("vehicle_plate", ""))
    config["vehicle_province"] = os.environ.get("ONTARIO_PARKS_PROVINCE", config.get("vehicle_province", "ONTARIO"))
    config["phone"] = os.environ.get("ONTARIO_PARKS_PHONE", config.get("phone", ""))
    config["telegram_token"] = os.environ.get("TELEGRAM_TOKEN", config.get("telegram_token", ""))
    config["telegram_chat_id"] = os.environ.get("TELEGRAM_CHAT_ID", config.get("telegram_chat_id", ""))
    config["gmail_app_password"] = os.environ.get("GMAIL_APP_PASSWORD", config.get("gmail_app_password", ""))
    config["previously_selected_park"] = config.get("previously_selected_park", "")
    
    return config

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

def escape_html(text):
    if not text:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def send_telegram_message(token, chat_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
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

def check_recent_email_after_transaction(config, transaction_type, transaction_time):
    """
    Polls IMAP for a new Ontario Parks email.
    transaction_type: 'book' or 'cancel'
    transaction_time: datetime.datetime (aware, in UTC)
    """
    email_user = config.get("email")
    app_password = config.get("gmail_app_password")
    if not email_user or not app_password:
        return {
            "status": "skipped",
            "message": "⚠️ Email verification skipped: Gmail credentials not configured."
        }
        
    print(f"Polling for new Ontario Parks email (type: {transaction_type})...")
    import email.utils
    
    mail = None
    def connect_imap():
        try:
            m = imaplib.IMAP4_SSL("imap.gmail.com", timeout=15)
            m.login(email_user, app_password)
            m.select("inbox")
            return m
        except Exception as conn_err:
            print(f"IMAP connection/login error: {conn_err}")
            return None
            
    mail = connect_imap()
    
    start_poll = time.time()
    while time.time() - start_poll < 60:
        try:
            if not mail:
                mail = connect_imap()
            if not mail:
                time.sleep(5)
                continue
                
            search_query = 'OR (FROM "confirmations@camis.com") (SUBJECT "Ontario Parks")'
            status, messages = mail.search(None, search_query)
            if status != "OK":
                status, messages = mail.search(None, '(SUBJECT "Ontario Parks")')
                
            if status == "OK" and messages[0]:
                mail_ids = messages[0].split()
                if mail_ids:
                    for m_id in reversed(mail_ids[-5:]):
                        status, data = mail.fetch(m_id, "(RFC822)")
                        if status == "OK":
                            raw_email = data[0][1]
                            msg = email.message_from_bytes(raw_email)
                            
                            subject_header = msg["Subject"] or ""
                            subject, encoding = decode_header(subject_header)[0]
                            if isinstance(subject, bytes):
                                subject = subject.decode(encoding or "utf-8", errors="ignore")
                                
                            sender = msg["From"] or ""
                            date_header = msg["Date"] or ""
                            
                            try:
                                email_dt = email.utils.parsedate_to_datetime(date_header)
                            except Exception:
                                email_dt = datetime.datetime.now(datetime.timezone.utc)
                                
                            if email_dt.tzinfo is None:
                                email_dt = email_dt.replace(tzinfo=datetime.timezone.utc)
                            else:
                                email_dt = email_dt.astimezone(datetime.timezone.utc)
                                
                            # Check date (allowing 60s clock skew)
                            if email_dt >= transaction_time - datetime.timedelta(seconds=60):
                                body = ""
                                if msg.is_multipart():
                                    for part in msg.walk():
                                        content_type = part.get_content_type()
                                        if content_type == "text/html":
                                            body = part.get_payload(decode=True).decode(errors="ignore")
                                            break
                                        elif content_type == "text/plain" and not body:
                                            body = part.get_payload(decode=True).decode(errors="ignore")
                                else:
                                    body = msg.get_payload(decode=True).decode(errors="ignore")
                                    
                                soup = BeautifulSoup(body, "html.parser")
                                text_content = soup.get_text()
                                
                                lower_subject = subject.lower()
                                lower_body = text_content.lower()
                                
                                is_cancel_subject = "cancel" in lower_subject or "cancellation" in lower_subject
                                is_cancel_body = "reservation has been cancelled" in lower_body or "cancellation confirmation" in lower_body
                                is_cancel = is_cancel_subject or is_cancel_body
                                
                                # Correlate type (skip confirmation emails when expecting cancellations, and vice-versa)
                                if transaction_type == "cancel" and not is_cancel:
                                    continue
                                if transaction_type == "book" and is_cancel:
                                    continue
                                    
                                # Extract summary
                                lines = [line.strip() for line in text_content.split("\n") if line.strip()]
                                summary_lines = []
                                for line in lines:
                                    if any(k in line.lower() for k in ["confirmation", "cancel", "permit", "vehicle", "plate", "amount", "total", "park", "status"]):
                                        if len(line) < 100 and line not in summary_lines:
                                            summary_lines.append(line)
                                            
                                summary = ", ".join(summary_lines[:4])
                                if not summary:
                                    summary = f"Subject: {subject}"
                                    
                                conclusion = "all good"
                                if transaction_type == "book":
                                    if "warning" in lower_body or "action required" in lower_body or "error" in lower_body:
                                        conclusion = "some issues to check (warnings found in email)"
                                        
                                try:
                                    mail.close()
                                    mail.logout()
                                except Exception:
                                    pass
                                    
                                local_dt = email_dt.astimezone()
                                time_str = local_dt.strftime("%I:%M:%S %p")
                                
                                return {
                                    "status": "found",
                                    "subject": subject,
                                    "sender": sender,
                                    "time": time_str,
                                    "summary": summary,
                                    "conclusion": conclusion
                                }
        except Exception as e:
            print(f"IMAP poll error: {e}")
            mail = None
            
        time.sleep(5)
        
    if mail:
        try:
            mail.close()
            mail.logout()
        except Exception:
            pass
            
    return {
        "status": "not_found",
        "message": f"⏳ No {transaction_type} email received yet. We will monitor your inbox in the background and notify you once it arrives.",
        "conclusion": "No email received yet. Monitoring in background..."
    }

def dismiss_cookie_consent(page):
    try:
        # Check for consent button for up to 5 seconds
        consent_btn = page.locator("button:has-text('I consent'), button:has-text('I Consent'), button#consentButton")
        for _ in range(5):
            if consent_btn.count() > 0 and consent_btn.first.is_visible():
                print("Clicking cookie consent banner...")
                consent_btn.first.click()
                time.sleep(1.5)
                break
            time.sleep(1)
    except Exception:
        pass

def dismiss_park_alerts(page):
    try:
        ack_btn = page.locator("button:has-text('Acknowledge'), button:has-text('acknowledge')")
        if ack_btn.count() > 0 and ack_btn.first.is_visible():
            print("Handling Park Alerts popup...")
            ack_btn.first.click()
            time.sleep(2)
    except Exception:
        pass

def wait_for_any_element(page, selectors, timeout=12000):
    if not selectors:
        return
    locators = [page.locator(s) for s in selectors]
    combined = locators[0]
    for loc in locators[1:]:
        combined = combined.or_(loc)
    try:
        combined.first.wait_for(state="attached", timeout=timeout)
    except Exception as e:
        print("Warning: wait_for_any_element timed out:", e)

def fetch_park_alerts(park_name):
    # Normalize name (e.g., "Sibbald Point" or "Sibbald Point Provincial Park" -> "sibbald point")
    normalized_target = park_name.lower().replace("provincial park", "").strip()
    
    url = "https://www.ontarioparks.ca/alerts"
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    alerts = []
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            
            # Loop through all p tags with strong
            for p in soup.find_all("p"):
                strong = p.find("strong")
                if strong:
                    text = strong.get_text().strip()
                    if "provincial park" in text.lower():
                        # Extract park name portion before the dash
                        parts = text.split("-", 1)
                        parsed_park_name = parts[0].strip()
                        parsed_normalized = parsed_park_name.lower().replace("provincial park", "").strip()
                        
                        if parsed_normalized == normalized_target:
                            alert_type = parts[1].strip() if len(parts) > 1 else "Notice"
                            # Find the next sibling paragraph for description
                            desc = ""
                            next_sib = p.find_next_sibling()
                            if next_sib and next_sib.name == "p":
                                desc = next_sib.get_text().strip()
                            
                            alerts.append({
                                "title": text,
                                "type": alert_type,
                                "description": desc
                            })
    except Exception as e:
        print(f"Error fetching alerts: {e}")
        
    return alerts

def create_browser_context(browser, user_agent):
    auth_state_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "auth_state.json")
    if os.path.exists(auth_state_path):
        try:
            context = browser.new_context(
                storage_state=auth_state_path,
                user_agent=user_agent,
                viewport={"width": 1280, "height": 800},
                extra_http_headers={"Accept-Language": "en-US,en;q=0.9"}
            )
            return context, True
        except Exception as e:
            print("Warning: Failed to load auth state, creating clean context:", e)
            
    context = browser.new_context(
        user_agent=user_agent,
        viewport={"width": 1280, "height": 800},
        extra_http_headers={"Accept-Language": "en-US,en;q=0.9"}
    )
    return context, False

def login_to_ontario_parks(page, email_user, password):
    print("Navigating to login page...")
    page.goto("https://reservations.ontarioparks.ca/login", timeout=40000)
    
    # Wait for either input#email OR redirect to /account
    is_logged_in = False
    for _ in range(20):
        if "account" in page.url:
            is_logged_in = True
            break
        if page.locator("input#email").count() > 0 and page.locator("input#email").first.is_visible():
            break
        time.sleep(0.5)
        
    if is_logged_in or "account" in page.url:
        print("Already logged in (redirected to account).")
        try:
            page.context.storage_state(path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "auth_state.json"))
        except Exception:
            pass
        return
    
    # Click consent if present
    consent_btn = page.locator("button:has-text('I consent'), button:has-text('I Consent')")
    if consent_btn.count() > 0 and consent_btn.first.is_visible():
        consent_btn.first.click()
        time.sleep(0.5)
        
    print("Submitting credentials...")
    page.locator("input#email").first.fill(email_user)
    page.locator("input#password").first.fill(password)
    page.locator("#loginButton").first.click()
    
    print("Submitted credentials, waiting for navigation...")
    try:
        page.wait_for_url("**/account**", timeout=8000)
    except Exception:
        time.sleep(3)
    page.wait_for_load_state("networkidle")
    
    # Save storage state on successful login
    try:
        page.context.storage_state(path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "auth_state.json"))
        print("Authentication state saved successfully.")
    except Exception as e:
        print("Warning: Could not save auth state:", e)
    page.wait_for_load_state("networkidle")

def handle_step_feedback(step_name, description, screenshot_name, page, request_approval_callback, progress_callback):
    screenshot_path = os.path.join(os.path.dirname(__file__), screenshot_name)
    try:
        page.screenshot(path=screenshot_path)
    except Exception as e:
        print("Warning: Failed to capture step screenshot:", e)
        
    print(f"[PROGRESS] Step: {step_name} | Desc: {description} | Image: {screenshot_name}", flush=True)

    if progress_callback:
        try:
            progress_callback(step_name, description, screenshot_path)
        except Exception as e:
            print("Warning: Progress callback failed:", e)
            
    if request_approval_callback:
        return request_approval_callback(step_name, description, screenshot_path)
        
    return True

def run_checkout_wizard(page, config, request_approval_callback=None, is_headless=True, progress_callback=None):
    """
    Scans and automates the sequential checkout wizard panels headlessly.
    """
    print("\nStarting automated checkout wizard...")
    for attempt in range(25):
        dismiss_cookie_consent(page)
        # 0. Handle landing on dashboard / My Account with item in cart
        if "account" in page.url and page.locator("a:has-text('Cart'), button:has-text('Cart')").count() > 0:
            cart_icon = page.locator("a:has-text('Cart'), button:has-text('Cart')").first
            if "0 Item" not in cart_icon.inner_text():
                print("Wizard: Found items in cart on account page. Clicking Cart icon to checkout...")
                if not is_headless:
                    input("\n[Headed Debug] Found items in cart on My Account. Press Enter to open Cart...")
                cart_icon.click()
                time.sleep(4)
                page.wait_for_load_state("networkidle")
                continue

        # 0.5. Handle landing on login page during checkout
        email_input = page.locator("input[type='email'], input#email, input[formcontrolname='email']")
        if email_input.count() > 0 and email_input.first.is_visible():
            password = config.get("ontario_parks_password")
            if not password:
                print("Wizard Error: Login prompt detected but password is not configured!")
                return False
            print("Wizard: Login prompt detected. Submitting credentials...")
            page.locator("input#email").first.fill(config["email"])
            page.locator("input#password").first.fill(password)
            page.locator("#loginButton").first.click()
            time.sleep(5)
            page.wait_for_load_state("networkidle")
            continue

        # 1. Review Reservation Details checkbox + confirm (Screenshot 3)
        review_chk_parent = page.locator("mat-checkbox:has-text('details are correct'), mat-checkbox")
        review_chk_input = page.locator("mat-checkbox:has-text('details are correct') input, mat-checkbox input")
        review_btn = page.locator("button:has-text('Confirm reservation details')")
        if review_btn.count() > 0 and review_btn.first.is_visible():
            print("Wizard: Confirming reservation details...")
            if review_chk_input.count() > 0 and not review_chk_input.first.is_checked():
                try:
                    review_chk_input.first.check(force=True)
                except Exception:
                    review_chk_parent.first.click()
                time.sleep(1)
            approved = handle_step_feedback("1. Review Details", "Checked 'Details are correct' checkbox.", "debug_step_1.png", page, request_approval_callback, progress_callback)
            if not approved:
                return False
            if not is_headless:
                input("\n[Headed Debug] Step 1: Details are checked. Press Enter to click 'Confirm reservation details'...")
            review_btn.first.click()
            time.sleep(3)
            page.wait_for_load_state("networkidle")
            continue
            
        # 2. Shopping Cart proceed (Screenshot 4)
        cart_btn = page.locator("button:has-text('Proceed to checkout')")
        if cart_btn.count() > 0 and cart_btn.first.is_visible():
            print("Wizard: Proceeding to checkout from shopping cart...")
            approved = handle_step_feedback("2. Shopping Cart", "Ready to click 'Proceed to checkout'.", "debug_step_2.png", page, request_approval_callback, progress_callback)
            if not approved:
                return False
            if not is_headless:
                input("\n[Headed Debug] Step 2: Shopping Cart. Press Enter to click 'Proceed to checkout'...")
            cart_btn.first.click()
            time.sleep(3)
            page.wait_for_load_state("networkidle")
            continue
            
        # 3. Policies Checkbox & Acknowledgement (Screenshot 6)
        policies_chk_parent = page.locator("mat-checkbox:has-text('agree'), mat-checkbox")
        policies_chk_input = page.locator("mat-checkbox:has-text('agree') input, mat-checkbox input")
        policies_btn = page.locator("button:has-text('Confirm acknowledgements')")
        if policies_btn.count() > 0 and policies_btn.first.is_visible():
            print("Wizard: Confirming policies acknowledgements...")
            if policies_chk_input.count() > 0 and not policies_chk_input.first.is_checked():
                try:
                    policies_chk_input.first.check(force=True)
                except Exception:
                    policies_chk_parent.first.click()
                time.sleep(1)
            approved = handle_step_feedback("3. Policies & Rules", "Checked 'Agree to rules' checkbox.", "debug_step_3.png", page, request_approval_callback, progress_callback)
            if not approved:
                return False
            if not is_headless:
                input("\n[Headed Debug] Step 3: Rules checked. Press Enter to click 'Confirm acknowledgements'...")
            policies_btn.first.click()
            time.sleep(3)
            page.wait_for_load_state("networkidle")
            continue
            
        # 4. Confirm Account Info (Screenshot 7)
        acc_btn = page.locator("button:has-text('Confirm account details')")
        if acc_btn.count() > 0 and acc_btn.first.is_visible():
            print("Wizard: Confirming account details...")
            approved = handle_step_feedback("4. Account Details", "Ready to click 'Confirm account details'.", "debug_step_4.png", page, request_approval_callback, progress_callback)
            if not approved:
                return False
            if not is_headless:
                input("\n[Headed Debug] Step 4: Account Details. Press Enter to click 'Confirm account details'...")
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
            approved = handle_step_feedback("5. Occupant details", "Selected 'I will be the occupant'.", "debug_step_5.png", page, request_approval_callback, progress_callback)
            if not approved:
                return False
            if not is_headless:
                input("\n[Headed Debug] Step 5: Occupant selected. Press Enter to click 'Confirm occupant'...")
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
                
            approved = handle_step_feedback("6. Vehicle & Permit Info", f"Filled Plate: {config['vehicle_plate']}, Permit: {config['permit_number']}.", "debug_step_6.png", page, request_approval_callback, progress_callback)
            if not approved:
                return False
            if not is_headless:
                input("\n[Headed Debug] Step 6: Vehicle plate and Permit filled. Press Enter to click 'Confirm additional information'...")
            additional_btn.first.click()
            time.sleep(3)
            page.wait_for_load_state("networkidle")
            continue
            
        # 7. Final Confirmation (Screenshot 10)
        confirm_btn = page.locator("button:has-text('Confirm booking')")
        if confirm_btn.count() > 0 and confirm_btn.first.is_visible():
            print("Wizard: Finalizing and clicking Confirm Booking...")
            try:
                page_text = page.locator("body").inner_text()
                import re
                amount_match = re.search(r"Total\s*(?:\(CAD\))?\s*\$(\d+(?:\.\d{2})?)", page_text, re.IGNORECASE)
                if amount_match:
                    config["final_amount"] = f"${amount_match.group(1)}"
                    print(f"Wizard: Extracted payment amount: {config['final_amount']}")
            except Exception as e:
                print("Warning: Could not extract amount:", e)
            approved = handle_step_feedback("7. Final Checkout", "Ready to click 'Confirm booking' to finalize reservation.", "debug_step_7.png", page, request_approval_callback, progress_callback)
            if not approved:
                return False
            if not is_headless:
                input("\n[Headed Debug] Step 7: Ready to book! Press Enter to finalize and book (THIS WILL PLACE A REAL RESERVATION!)...")
            confirm_btn.first.click()
            time.sleep(5)
            page.wait_for_load_state("networkidle")
            continue
            
        # 8. Success page checking (Screenshot 11)
        if "Success!" in page.locator("body").inner_text() or page.locator("text=Success!").count() > 0:
            print("Wizard complete: Success page reached!")
            break
            
        time.sleep(2)
    return True

def list_reservations(email_user, password, headless=True):
    print("Launching browser to list reservations...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        
        context, has_auth = create_browser_context(browser, user_agent)
        page = context.new_page()
        page.add_init_script("delete navigator.__proto__.webdriver;")
        
        logged_in = False
        if has_auth:
            print("Attempting direct navigation with cached session...")
            try:
                page.goto("https://reservations.ontarioparks.ca/account/all-bookings", timeout=15000)
                # Wait for any indicative loaded elements to appear on either page state (excluding base header layouts)
                wait_for_any_element(page, ["section.compact-booking", "text=No active reservations", "input#email"], timeout=12000)
                if (page.locator("section.compact-booking").count() > 0 or 
                    page.locator("text=No active reservations").count() > 0):
                    logged_in = True
                    print("Session cache hit!")
            except Exception as e:
                print("Direct navigation failed:", e)
                
        if not logged_in:
            print("Session cache miss or expired, performing full login...")
            login_to_ontario_parks(page, email_user, password)
            print("Navigating to My Reservations...")
            page.goto("https://reservations.ontarioparks.ca/account/all-bookings", timeout=40000)
            wait_for_any_element(page, ["section.compact-booking", "text=No active reservations"], timeout=12000)
        time.sleep(1)
        
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

def cancel_reservation(email_user, password, target_res_num, headless=True, skip_email_check=False):
    transaction_time = datetime.datetime.now(datetime.timezone.utc)
    print(f"Launching browser to cancel reservation {target_res_num}...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        context, has_auth = create_browser_context(browser, user_agent)
        page = context.new_page()
        page.add_init_script("delete navigator.__proto__.webdriver;")
        
        logged_in = False
        if has_auth:
            print("Attempting direct navigation with cached session...")
            try:
                page.goto("https://reservations.ontarioparks.ca/account/all-bookings", timeout=15000)
                # Wait for any indicative loaded elements to appear on either page state (excluding base header layouts)
                wait_for_any_element(page, ["section.compact-booking", "text=No active reservations", "input#email"], timeout=12000)
                if (page.locator("section.compact-booking").count() > 0 or 
                    page.locator("text=No active reservations").count() > 0):
                    logged_in = True
                    print("Session cache hit!")
            except Exception as e:
                print("Direct navigation failed:", e)
                
        if not logged_in:
            print("Session cache miss or expired, performing full login...")
            login_to_ontario_parks(page, email_user, password)
            print("Navigating to My Reservations...")
            page.goto("https://reservations.ontarioparks.ca/account/all-bookings", timeout=40000)
            wait_for_any_element(page, ["section.compact-booking", "text=No active reservations"], timeout=12000)
        time.sleep(1)
        
        # Locate card containing the target reservation number
        card = page.locator("section.compact-booking, app-compact-booking, mat-card, .mat-card", has_text=target_res_num)
        
        cancel_btn = card.locator("button:has-text('Cancel reservation'), a:has-text('Cancel reservation')")
        if cancel_btn.count() > 0 and cancel_btn.first.is_visible():
            print("Found Cancel button! Clicking it...")
            cancel_btn.first.click()
            time.sleep(5)
            page.wait_for_load_state("networkidle")
            
            # Step 1: Acknowledgement
            chk = page.locator("mat-checkbox:has-text('I acknowledge') input, mat-checkbox input")
            if chk.count() > 0:
                print("Checking acknowledgement checkbox...")
                chk.first.check(force=True)
                time.sleep(1)
            else:
                print("Acknowledgment checkbox not found, trying parent click...")
                page.locator("mat-checkbox").first.click()
                time.sleep(1)
                
            proceed_btn = page.locator("button:has-text('Proceed')")
            if proceed_btn.count() > 0:
                print("Clicking Proceed...")
                proceed_btn.first.click()
                time.sleep(5)
                page.wait_for_load_state("networkidle")
                
                # Step 2: Confirmation
                confirm_btn = page.locator("button:has-text('Confirm cancellation')")
                if confirm_btn.count() > 0:
                    print("Confirming cancellation...")
                    confirm_btn.first.click()
                    time.sleep(5)
                    page.wait_for_load_state("networkidle")
                    print(f"Reservation {target_res_num} cancelled successfully!")
                    browser.close()
                    
                    config = load_config()
                    if config.get("telegram_chat_id"):
                        cancel_msg = f"❌ <b>Reservation <a href=\"https://reservations.ontarioparks.ca/account/all-bookings\">{target_res_num}</a> has been successfully cancelled!</b>"
                        send_telegram_message(config["telegram_token"], config["telegram_chat_id"], cancel_msg)
                        
                        if not skip_email_check:
                            # Poll and post cancellation email verification
                            result = check_recent_email_after_transaction(config, "cancel", transaction_time)
                            if result["status"] == "found":
                                safe_sender = escape_html(result['sender'])
                                safe_subject = escape_html(result['subject'])
                                safe_summary = escape_html(result['summary'])
                                verify_msg = (
                                    f"✉️ <b>Ontario Parks Email Verification:</b>\n"
                                    f"📥 Checked for email from Ontario Parks.\n\n"
                                    f"📧 <b>Sender:</b> {safe_sender}\n"
                                    f"📅 <b>Time:</b> {result['time']}\n"
                                    f"📝 <b>Subject:</b> {safe_subject}\n"
                                    f"🔍 <b>Summary:</b> {safe_summary}\n\n"
                                    f"🤖 <b>Conclusion:</b> <b>{result['conclusion']}</b>"
                                )
                            elif result["status"] == "not_found":
                                verify_msg = (
                                    f"✉️ <b>Ontario Parks Email Verification:</b>\n"
                                    f"📥 Checked for email from Ontario Parks.\n\n"
                                    f"{result['message']}\n\n"
                                    f"🤖 <b>Conclusion:</b> <b>{result['conclusion']}</b>"
                                )
                            else:
                                verify_msg = result["message"]
                                
                            send_telegram_message(config["telegram_token"], config["telegram_chat_id"], verify_msg)
                    
                    return True
                else:
                    print("Error: Confirm cancellation button not found on step 2!")
            else:
                print("Error: Proceed button not found on step 1!")
        else:
            print(f"Error: Could not find active 'Cancel reservation' button for {target_res_num}.")
            
        browser.close()
        return False

def run_booking_flow(config, target_park_override=None, target_date_override=None, is_headless=True, request_approval_callback=None, progress_callback=None, forecast_only=False, skip_email_check=False):
    transaction_time = datetime.datetime.now(datetime.timezone.utc)
    config["final_amount"] = "Unknown"
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
                return False
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
    
    if forecast_only:
        print("\n[Weather/Wind] Fetching wind forecasts for participating kiting parks...")
        for name, info in PARKS.items():
            forecast = fetch_weather_forecast(info["lat"], info["lon"], target_date_str)
            if forecast:
                print(f" - {name:<30} | Wind: {forecast['max_speed']:>4} kts (Gust: {forecast['max_gust']:>4} kts) | {forecast['condition']}")
        return True
        
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
        clean_override = target_park_override.split("(")[0].replace("Provincial Park", "").strip().lower()
        for p in ranked_parks:
            clean_p = p["name"].replace("Provincial Park", "").strip().lower()
            if clean_override in clean_p or clean_p in clean_override:
                selected_park = p
                break
        if not selected_park:
            print(f"Error: Overridden park name '{target_park_override}' could not be matched!")
            return False
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
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        context, has_auth = create_browser_context(browser, user_agent)
        page = context.new_page()
        page.add_init_script("delete navigator.__proto__.webdriver;")
        
        print("Navigating to homepage...")
        page.goto("https://reservations.ontarioparks.ca/", timeout=40000)
        
        # Wait for full load and let Angular app render
        page.wait_for_load_state("load")
        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass
            
        dismiss_cookie_consent(page)
        
        print("Opening Day Use section...")
        day_use_tab = page.locator("#mat-tab-link-1, a:has-text('Day Use'), .mat-tab-link:has-text('Day Use')")
        try:
            day_use_tab.first.wait_for(state="visible", timeout=10000)
        except Exception as e:
            print("Warning: Day Use tab not visible yet:", e)
            
        day_use_tab.first.click()
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
        dismiss_park_alerts(page)
        
        # Handle multi-location selection page (e.g. Wasaga Beach with multiple Areas)
        list_toggle = page.locator("#list-view-button-button")
        if list_toggle.count() > 0 and list_toggle.is_visible():
            print("Multi-location selection page detected. Switching to List view...")
            list_toggle.click()
            time.sleep(3)
            
            options = page.locator("button.map-link-button, a.map-link-button").all()
            target_option = None
            
            # Match preferred "Area 6" first
            for opt in options:
                txt = opt.text_content() or ""
                if "Area 6" in txt and "Available" in txt:
                    target_option = opt
                    break
                    
            # Fallback to any available area
            if not target_option:
                for opt in options:
                    txt = opt.text_content() or ""
                    if "Available" in txt:
                        target_option = opt
                        break
                        
            if target_option:
                area_name = (target_option.text_content() or "").strip().replace("\n", " ")
                print(f"Selecting sub-location: '{area_name}'...")
                target_option.click()
                time.sleep(5)
                dismiss_park_alerts(page)
            else:
                print("Error: No available sub-locations found on the selection page!")
                browser.close()
                return False
                
        consent_btn = page.locator("#consentButton")
        if consent_btn.count() > 0 and consent_btn.is_visible():
            print("Accepting rules consent...")
            consent_btn.click()
            time.sleep(2)
            
        print("Waiting for grid cells to load...")
        try:
            page.locator("table.chart td.chart-cell").first.wait_for(state="visible", timeout=12000)
        except Exception:
            print("Warning: Timeout waiting for chart cells to become visible.")

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
            return False
            
        # Find correct row index dynamically matching "day use"
        row_index = -1
        rows = page.locator("table.chart tr").all()
        for idx in range(1, len(rows)):
            row_cells = rows[idx].locator("td, th").all()
            if row_cells:
                row_header_text = row_cells[0].inner_text().strip()
                if "day use" in row_header_text.lower() or "dayuse" in row_header_text.lower():
                    row_index = idx
                    break
        if row_index == -1:
            print("Warning: 'DVP - Day Use' row not found dynamically, falling back to first row.")
            row_index = 1
        else:
            print(f"Selected row index {row_index} matching Day Use activity.")
            
        row_cells = rows[row_index].locator("td, th").all()
        cell = row_cells[col_index]
        label = cell.get_attribute("aria-label") or ""
        
        if "Available" not in label:
            print(f"Error: Daily Vehicle Permit for {park_name} on {target_date_str} is NOT available!")
            print(f"Cell label content: '{label}'")
            browser.close()
            return False
            
        print("Permit is available! Selecting day slot...")
        cell.click()
        time.sleep(2)
        dismiss_park_alerts(page)
        
        print("Clicking Reserve...")
        page.click("#reserveButton")
        time.sleep(5)
        dismiss_park_alerts(page)
        page.wait_for_load_state("networkidle")
        
        password = config.get("ontario_parks_password")
        if is_headless and not password:
            print("Error: Headless run selected, but 'ontario_parks_password' is not configured!")
            browser.close()
            return False
            
        if password:
            # Check if login prompt is visible (without navigating away and losing returnUrl)
            email_input = page.locator("input[type='email'], input#email, input[formcontrolname='email']")
            if email_input.count() > 0 and email_input.first.is_visible():
                print("Login prompt detected. Submitting credentials...")
                page.locator("input#email").first.fill(config["email"])
                page.locator("input#password").first.fill(password)
                page.locator("#loginButton").first.click()
                print("Submitted credentials, waiting for navigation...")
                time.sleep(6)
                page.wait_for_load_state("networkidle")
            else:
                print("No login prompt detected, proceeding...")
        else:
            print("\n" + "*"*80)
            print("⚠️ ACTION REQUIRED: If you are not signed in, please log in to your Ontario Parks")
            print("account now in the opened browser window.")
            print("Once you are signed in and see the checkout wizard or additional info page, press Enter here.")
            print("*"*80)
            input_with_timeout("\nPress Enter to continue after logging in (Timeout in 180s)...", timeout=180, default="")
            
        wizard_success = run_checkout_wizard(page, config, request_approval_callback, is_headless, progress_callback)
        if not wizard_success:
            print("Wizard aborted or failed.")
            browser.close()
            return False
            
        print("\nScanning page for reservation number...")
        conf_number = "Unknown"
        page_text = page.locator("body").inner_text()
        
        import re
        match = re.search(r"INOP\d+-[A-Z0-9]+|INOP\d+-\d+|OP-[A-Z0-9]+", page_text)
        if match:
            conf_number = match.group(0)
            print(f"Captured confirmation number: {conf_number}")
        else:
            match_any = re.search(r"Reservation\s*(?:Number|#)?\s*:?\s*([A-Z0-9\-]{5,})", page_text, re.IGNORECASE)
            if match_any:
                temp_num = match_any.group(1).strip()
                if temp_num.lower() not in ["support", "details", "information", "reservations", "account"]:
                    conf_number = temp_num
                    print(f"Captured confirmation number: {conf_number}")
                
        screenshot_name = f"confirmation_{target_date_str}_{conf_number.replace('-', '_')}.png"
        screenshot_path = os.path.join(os.path.dirname(__file__), screenshot_name)
        page.screenshot(path=screenshot_path)
        print(f"Saved confirmation screenshot to {screenshot_path}")
        
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

        if conf_number == "Unknown":
            print("Error: Booking process failed or confirmation number could not be found.")
            browser.close()
            return False
            
        # Capture final amount if not found earlier
        amount_str = config.get("final_amount", "Unknown")
        if amount_str == "Unknown":
            amount_match = re.search(r"(?:Total|Paid|Amount)\s*(?:\(CAD\))?\s*:?\s*\$(\d+(?:\.\d{2})?)", page_text, re.IGNORECASE)
            if amount_match:
                amount_str = f"${amount_match.group(1)}"
        print(f"Captured transaction amount: {amount_str}")
        config["final_amount"] = amount_str
        save_config(config)
            
        browser.close()
        
    if config.get("gmail_app_password"):
        email_verified = "Pending ✉️"
    else:
        email_verified = "Not configured (skipped)"
            
    # Fetch park alerts
    alerts = fetch_park_alerts(park_name)
    if alerts:
        alert_lines = []
        for a in alerts:
            desc = a["description"].replace("\n", " ")
            alert_lines.append(f"• <b>{a['type']}:</b> {desc}")
        alerts_text = "\n".join(alert_lines)
    else:
        alerts_text = "✅ No active alerts. Safe for swimming! 🏊‍♂️"

    msg_text = (
        f"🌊 <b>Ontario Park Reservation Confirmed!</b> 🌊\n\n"
        f"📍 <b>Park:</b> {park_name}\n"
        f"📅 <b>Date:</b> {target_label} ({target_date_str})\n"
        f"🚗 <b>Vehicle:</b> {config['vehicle_plate']} ({config['vehicle_province']})\n"
        f"🎫 <b>Permit:</b> {config['permit_number']}\n"
        f"💰 <b>Amount:</b> {amount_str}\n"
        f"🔑 <b>Confirmation #:</b> <a href=\"https://reservations.ontarioparks.ca/account/all-bookings\">{conf_number}</a>\n"
        f"📧 <b>Email verified:</b> {email_verified}\n\n"
        f"🚨 <b>Park Alerts:</b>\n{alerts_text}\n\n"
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
            
        if not skip_email_check:
            # Poll for new transaction email and post verification status
            result = check_recent_email_after_transaction(config, "book", transaction_time)
            if result["status"] == "found":
                safe_sender = escape_html(result['sender'])
                safe_subject = escape_html(result['subject'])
                safe_summary = escape_html(result['summary'])
                verify_msg = (
                    f"✉️ <b>Ontario Parks Email Verification:</b>\n"
                    f"📥 Checked for email from Ontario Parks.\n\n"
                    f"📧 <b>Sender:</b> {safe_sender}\n"
                    f"📅 <b>Time:</b> {result['time']}\n"
                    f"📝 <b>Subject:</b> {safe_subject}\n"
                    f"🔍 <b>Summary:</b> {safe_summary}\n\n"
                    f"🤖 <b>Conclusion:</b> <b>{result['conclusion']}</b>"
                )
            elif result["status"] == "not_found":
                verify_msg = (
                    f"✉️ <b>Ontario Parks Email Verification:</b>\n"
                    f"📥 Checked for email from Ontario Parks.\n\n"
                    f"{result['message']}\n\n"
                    f"🤖 <b>Conclusion:</b> <b>{result['conclusion']}</b>"
                )
            else:
                verify_msg = result["message"]
                
            send_telegram_message(config["telegram_token"], config["telegram_chat_id"], verify_msg)
    else:
        print("\nTelegram chat ID not configured, skipped notification.")
        print("Formatted message:")
        print(msg_text.replace("<b>", "").replace("</b>", "").replace("<code>", "").replace("</code>", ""))
        
    return True

def main():
    config = load_config()
    
    parser = argparse.ArgumentParser(description="Ontario Parks Reservation Helper")
    subparsers = parser.add_subparsers(dest="command")
    
    # Subcommands
    # Subcommands
    book_parser = subparsers.add_parser("book", help="Book a daily vehicle permit")
    book_parser.add_argument("--park", help="Name of the park (e.g. 'Sibbald Point')")
    book_parser.add_argument("--date", help="Date: 'today', 'tomorrow', 'day_after', or YYYY-MM-DD")
    book_parser.add_argument("--headless", type=str, choices=["true", "false"], default="true", help="Run headlessly")
    book_parser.add_argument("--skip-email-check", action="store_true", help="Skip email verification check")
    
    list_parser = subparsers.add_parser("list", help="List active reservations")
    list_parser.add_argument("--headless", type=str, choices=["true", "false"], default="true")
    
    cancel_parser = subparsers.add_parser("cancel", help="Cancel a reservation")
    cancel_parser.add_argument("--reservation", required=True, help="Reservation Receipt Number to cancel")
    cancel_parser.add_argument("--headless", type=str, choices=["true", "false"], default="true")
    cancel_parser.add_argument("--skip-email-check", action="store_true", help="Skip email verification check")
    
    parser.add_argument("--forecast-only", action="store_true", help="Only show weather/wind forecast for today, tomorrow, and day after")
    parser.add_argument("--setup-telegram", action="store_true", help="Interact and resolve Telegram Chat ID dynamically")
    
    args = parser.parse_args()
    
    if args.setup_telegram:
        chat_id = resolve_telegram_chat_id(config["telegram_token"])
        if chat_id:
            config["telegram_chat_id"] = chat_id
            save_config(config)
            send_telegram_message(config["telegram_token"], chat_id, "⚙️ Telegram integration successfully verified!")
            print("Telegram Chat ID updated and test message sent successfully.")
        sys.exit(0)
        
    if args.command == "list":
        password = config.get("ontario_parks_password")
        if not password:
            print("Error: 'ontario_parks_password' is not configured!")
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
            print("Error: 'ontario_parks_password' is not configured!")
            sys.exit(1)
        headless = args.headless == "true"
        success = cancel_reservation(config["email"], password, args.reservation, headless=headless, skip_email_check=args.skip_email_check)
        if success:
            sys.exit(0)
        else:
            sys.exit(1)
            
    is_headless = True
    target_park_override = None
    target_date_override = None
    skip_email_check = False
    
    if args.command == "book":
        is_headless = args.headless == "true"
        target_park_override = args.park
        target_date_override = args.date
        skip_email_check = args.skip_email_check
        
    success = run_booking_flow(
        config,
        target_park_override=target_park_override,
        target_date_override=target_date_override,
        is_headless=is_headless,
        forecast_only=args.forecast_only,
        skip_email_check=skip_email_check
    )
    if success:
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
