import subprocess
import time
import requests
import json
import os
import sys
import threading
import datetime
import calendar
import imaplib
import email
from email.header import decode_header
import email.utils
from bs4 import BeautifulSoup

# Add current dir to path to import reserve
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from reserve import load_config, send_telegram_message, run_booking_flow, escape_html, check_recent_email_after_transaction
import re

def is_future_or_today(date_str):
    if not date_str:
        return False
    try:
        # date_str is e.g. "Sun Jul 19"
        parts = date_str.split()
        if len(parts) >= 3:
            month_name = parts[1] # e.g. "Jul"
            day_num = int(parts[2]) # e.g. 19
            month_num = list(calendar.month_abbr).index(month_name[:3].title())
            current_year = datetime.date.today().year
            email_date = datetime.date(current_year, month_num, day_num)
            
            today = datetime.date.today()
            # If the email date is in Jan but today is Dec, assume it belongs to next year
            if (today - email_date).days > 180:
                email_date = datetime.date(current_year + 1, month_num, day_num)
                
            # Allow yesterday's dates as well just in case they land late or bot checks late
            return email_date >= today - datetime.timedelta(days=1)
    except Exception as ex:
        print(f"Error parsing date {date_str}: {ex}")
    return False

USER_STATE = None
op_lock = threading.Lock()
CURRENT_OPERATION = None
LAST_ERROR = "No errors recorded."

def acquire_operation(op_name):
    global CURRENT_OPERATION
    with op_lock:
        if CURRENT_OPERATION is not None:
            return False
        CURRENT_OPERATION = op_name
        return True

def release_operation():
    global CURRENT_OPERATION
    with op_lock:
        CURRENT_OPERATION = None

def background_email_monitor(transaction_type, transaction_time):
    # Wait 60 seconds first to let things settle and avoid redundant initial checks
    time.sleep(60)
    
    token = config["telegram_token"]
    chat_id = config["telegram_chat_id"]
    
    print(f"Starting background email monitor for {transaction_type} at {transaction_time}...")
    for attempt in range(5):
        result = check_recent_email_after_transaction(config, transaction_type, transaction_time)
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
            send_telegram_message(token, chat_id, verify_msg)
            return
        time.sleep(60)
        
    # If still not found after 5 minutes
    send_telegram_message(
        token, chat_id,
        f"⚠️ <b>Email Verification Timeout:</b> No {transaction_type} confirmation email found in your inbox after 10 minutes."
    )

def run_self_test_flow():
    token = config["telegram_token"]
    chat_id = config["telegram_chat_id"]
    
    # Try to lock the bot. If already busy, wait up to 30 minutes (checking every 5 mins)
    acquired = False
    for _ in range(6):
        if acquire_operation("Weekly Self-Test"):
            acquired = True
            break
        time.sleep(300)
        
    if not acquired:
        send_telegram_message(token, chat_id, "⚠️ <b>Weekly Self-Test Aborted:</b> The bot was busy with another operation for over 30 minutes.")
        return
        
    try:
        import random
        park = random.choice(["Sibbald Point", "Presqu'ile", "Wasaga Beach"])
        
        today = datetime.date.today()
        # Wednesday is weekday = 2 (Monday is 0)
        days_ahead = 2 - today.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        target_date = today + datetime.timedelta(days=days_ahead)
        target_date_str = target_date.strftime("%Y-%m-%d")
        
        send_telegram_message(
            token, chat_id,
            f"🧪 <b>Weekly Self-Test Started:</b>\n"
            f"🌲 <b>Park:</b> {park}\n"
            f"📅 <b>Date:</b> Wednesday ({target_date_str})\n\n"
            f"⌛ <i>Attempting automated booking...</i>"
        )
        
        # Book the park
        args = [sys.executable, "reserve.py", "book", "--park", park, "--date", target_date_str, "--headless", "true", "--skip-email-check"]
        metadata = {}
        booking_success = run_subprocess_with_progress(args, f"Self-Test Booking {park}", 360, out_metadata=metadata)
        
        conf_num = metadata.get("conf_number")
        
        if not booking_success or not conf_num:
            send_telegram_message(
                token, chat_id,
                f"❌ <b>Weekly Self-Test Failed:</b> Booking failed or confirmation number could not be found.\n"
                f"Use 'Check Errors' for details."
            )
            return
            
        send_telegram_message(
            token, chat_id,
            f"✅ <b>Weekly Self-Test - Booking Successful!</b>\n"
            f"🔑 <b>Confirmation #:</b> {conf_num}\n\n"
            f"⌛ <i>Attempting automated cancellation...</i>"
        )
        
        # Wait 5 seconds to let system settle
        time.sleep(5)
        
        # Cancel the booking
        cancel_args = [sys.executable, "reserve.py", "cancel", "--reservation", conf_num, "--headless", "true", "--skip-email-check"]
        res = subprocess.run(cancel_args, capture_output=True, text=True, timeout=90)
        
        if res.returncode == 0:
            send_telegram_message(
                token, chat_id,
                f"✅ <b>Weekly Self-Test Completed Successfully!</b>\n"
                f"❌ Reservation <b>{conf_num}</b> was successfully cancelled."
            )
        else:
            global LAST_ERROR
            LAST_ERROR = f"Self-Test Cancellation failed with code {res.returncode}.\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
            send_telegram_message(
                token, chat_id,
                f"⚠️ <b>Weekly Self-Test Issue:</b> Booking was successful, but automated cancellation failed.\n"
                f"Please cancel reservation <b>{conf_num}</b> manually.\n"
                f"Use 'Check Errors' for details."
            )
            
    except Exception as e:
        send_telegram_message(token, chat_id, f"❌ <b>Weekly Self-Test Exception:</b> {e}")
    finally:
        release_operation()

def selftest_loop():
    time.sleep(60) # Wait 60 seconds after bot boot
    while True:
        try:
            now = datetime.datetime.now() # Local time
            # Check if it is Monday (weekday = 0) and the hour is 7am
            if now.weekday() == 0 and now.hour == 7:
                last_date = ""
                json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "last_selftest.json")
                if os.path.exists(json_path):
                    with open(json_path, "r", encoding="utf-8") as f:
                        try:
                            data = json.load(f)
                            last_date = data.get("last_run_date", "")
                        except Exception:
                            pass
                
                today_str = now.strftime("%Y-%m-%d")
                if last_date != today_str:
                    # Persist run date immediately to avoid duplicate runs
                    with open(json_path, "w", encoding="utf-8") as f:
                        json.dump({"last_run_date": today_str}, f)
                    
                    threading.Thread(target=run_self_test_flow, daemon=True).start()
        except Exception as e:
            print(f"Error in selftest_loop: {e}")
        time.sleep(60)

def run_subprocess_with_progress(args, op_name, timeout_secs, out_metadata=None):
    global LAST_ERROR
    token = config["telegram_token"]
    chat_id = config["telegram_chat_id"]
    
    proc = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1
    )
    
    start_time = time.time()
    timer = threading.Timer(timeout_secs, proc.kill)
    try:
        timer.start()
        stdout_lines = []
        for line in iter(proc.stdout.readline, ""):
            stdout_lines.append(line)
            if "Captured confirmation number:" in line:
                conf_match = re.search(r"Captured confirmation number:\s*(\S+)", line)
                if conf_match and out_metadata is not None:
                    out_metadata["conf_number"] = conf_match.group(1)
                    
            if line.startswith("[PROGRESS]"):
                parts = line.strip().split(" | ")
                step_name = ""
                desc = ""
                img_name = ""
                for part in parts:
                    if part.startswith("[PROGRESS] Step: "):
                        step_name = part.replace("[PROGRESS] Step: ", "")
                    elif part.startswith("Desc: "):
                        desc = part.replace("Desc: ", "")
                    elif part.startswith("Image: "):
                        img_name = part.replace("Image: ", "")
                if step_name and img_name:
                    img_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), img_name)
                    send_progress(step_name, desc, img_path)
                    
        proc.wait()
        
        if proc.returncode != 0:
            stderr = proc.stderr.read()
            stdout_full = "".join(stdout_lines)
            if proc.returncode == -9 or proc.returncode == 15 or (time.time() - start_time >= timeout_secs):
                LAST_ERROR = f"Operation '{op_name}' timed out after {timeout_secs} seconds.\nSTDOUT:\n{stdout_full}\nSTDERR:\n{stderr}"
                send_telegram_message(token, chat_id, f"❌ <b>{op_name} timed out ({timeout_secs}s limit).</b>")
            else:
                LAST_ERROR = f"Command failed with exit code {proc.returncode}.\nSTDOUT:\n{stdout_full}\nSTDERR:\n{stderr}"
                display_err = stderr[-300:] or stdout_full[-300:]
                send_telegram_message(token, chat_id, f"❌ <b>{op_name} failed:</b>\n<pre>{escape_html(display_err)}</pre>\nUse 'Check Errors' for full details.")
            return False
            
        return True
    except Exception as e:
        LAST_ERROR = f"Exception during subprocess run: {str(e)}"
        send_telegram_message(token, chat_id, f"❌ <b>{op_name} execution error:</b> {e}")
        return False
    finally:
        timer.cancel()

def add_recent_park(park_name):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "recent_parks.json")
    recent = []
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                recent = json.load(f)
        except Exception:
            pass
    # Normalize name (remove " Provincial Park" suffix)
    clean = park_name.replace(" Provincial Park", "").strip()
    if clean in recent:
        recent.remove(clean)
    recent.insert(0, clean)
    recent = recent[:5]
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(recent, f, indent=4)
    except Exception:
        pass

def get_recent_parks_keyboard():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "recent_parks.json")
    recent = []
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                recent = json.load(f)
        except Exception:
            pass
    if not recent:
        recent = ["Sibbald Point", "Presqu'ile", "Wasaga Beach"]
        
    rows = []
    row = []
    for p in recent:
        row.append({"text": f"🌲 {p}", "callback_data": f"park:{p}"})
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
        
    rows.append([
        {"text": "🔍 Search for another park", "callback_data": "search_park"}
    ])
    rows.append([
        {"text": "❌ Cancel", "callback_data": "cancel_wizard"}
    ])
    return {"inline_keyboard": rows}

def perform_park_search(query):
    global USER_STATE
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "all_parks.json")
    all_parks = []
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                all_parks = json.load(f)
        except Exception:
            pass
            
    matches = [p for p in all_parks if query.lower() in p.lower()]
    
    token = config["telegram_token"]
    chat_id = config["telegram_chat_id"]
    
    if not matches:
        send_telegram_message(
            token, chat_id,
            f"❌ No provincial parks matched your query: <b>{escape_html(query)}</b>\n"
            "Please try another name (or type <code>cancel</code> to exit search):"
        )
        return
        
    USER_STATE = None
    
    reply_text = f"🔍 <b>Search results for '{escape_html(query)}':</b>\nSelect a park to book:"
    rows = []
    row = []
    for p in matches[:10]:
        row.append({"text": f"🌲 {p}", "callback_data": f"park:{p}"})
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
        
    if len(matches) > 10:
        reply_text = f"🔍 <b>Found {len(matches)} matches (showing top 10).</b>\nSelect a park to book:"
        
    rows.append([
        {"text": "🔍 Search again", "callback_data": "search_park"},
        {"text": "❌ Cancel", "callback_data": "cancel_wizard"}
    ])
    
    send_telegram_keyboard(token, chat_id, reply_text, {"inline_keyboard": rows})

def check_and_notify_checkin_reminders():
    email_user = config.get("email")
    app_password = config.get("gmail_app_password")
    if not email_user or not app_password:
        return
        
    notified_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "notified_checkins.json")
    notified_ids = set()
    if os.path.exists(notified_file):
        try:
            with open(notified_file, "r") as f:
                notified_ids = set(json.load(f))
        except Exception:
            pass
            
    print("Checking Gmail for check-in reminders...")
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", timeout=15)
        mail.login(email_user, app_password)
        mail.select("inbox")
        
        search_query = '(FROM "confirmations@camis.com" SUBJECT "check in online")'
        status, messages = mail.search(None, search_query)
        if status == "OK" and messages[0]:
            mail_ids = messages[0].split()
            for m_id in mail_ids:
                status, header_data = mail.fetch(m_id, "(BODY[HEADER.FIELDS (MESSAGE-ID)])")
                if status == "OK":
                    header_text = header_data[0][1].decode(errors="ignore")
                    msg_id_match = re.search(r"Message-ID:\s*(<[^>]+>)", header_text, re.IGNORECASE)
                    if msg_id_match:
                        msg_id = msg_id_match.group(1)
                        if msg_id in notified_ids:
                            continue
                            
                        # Fetch full message
                        status, data = mail.fetch(m_id, "(RFC822)")
                        if status == "OK":
                            raw_email = data[0][1]
                            msg = email.message_from_bytes(raw_email)
                            
                            # Extract body
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
                            
                            # Parse checkin link
                            checkin_url = "https://reservations.ontarioparks.ca/account/all-bookings"
                            for a in soup.find_all("a", href=True):
                                if "check in" in a.get_text().lower() or "checkin" in a["href"].lower():
                                    checkin_url = a["href"]
                                    break
                                    
                            # Parse park name
                            park_match = re.search(r"arrive at\s+([^.]+?)\.", text_content, re.IGNORECASE)
                            park_name = park_match.group(1).strip() if park_match else "Ontario Parks"
                            
                            # Parse arrival date
                            lines = [l.strip() for l in text_content.split("\n") if l.strip()]
                            arrival_date = ""
                            for idx, line in enumerate(lines):
                                if line.lower() == "arrival":
                                    if idx + 1 < len(lines):
                                        arrival_date = lines[idx+1]
                                    break
                                    
                            # Skip if arrival_date is empty or in the past
                            if not arrival_date or not is_future_or_today(arrival_date):
                                print(f"Skipping outdated/invalid check-in reminder {msg_id} (Date: '{arrival_date}')")
                                notified_ids.add(msg_id)
                                continue
                                
                            # Escape text values for safety
                            safe_park = escape_html(park_name)
                            safe_date = escape_html(arrival_date)
                            
                            # Send Telegram notification card
                            verify_msg = (
                                f"🔔 <b>Ontario Parks Check-in Reminder!</b> 🔔\n\n"
                                f"📍 <b>Park:</b> {safe_park}\n"
                                f"📅 <b>Arrival Date:</b> {safe_date}\n\n"
                                f"👉 <a href=\"{checkin_url}\"><b>Check in online now</b></a>"
                            )
                            
                            print(f"Sending check-in reminder for Message-ID: {msg_id}...")
                            success = send_telegram_message(config["telegram_token"], config["telegram_chat_id"], verify_msg)
                            if success:
                                notified_ids.add(msg_id)
                                
        mail.close()
        mail.logout()
    except Exception as e:
        print(f"Error checking reminders: {e}")
        
    try:
        with open(notified_file, "w") as f:
            json.dump(list(notified_ids), f)
    except Exception:
        pass


def add_cached_booking(res_num, park_name, date_str):
    json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "active_reservations.json")
    reservations = []
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                reservations = json.load(f)
        except Exception:
            pass
            
    # Check if already exists to avoid duplicates
    for r in reservations:
        if r.get("reservation_number") == res_num:
            return
            
    # Add new booking
    reservations.append({
        "reservation_number": res_num,
        "park": park_name,
        "date": date_str,
        "vehicle": config.get("vehicle_plate", "ATXJ307"),
        "occupant": "I will be the occupant"
    })
    
    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(reservations, f, indent=2)
    except Exception as e:
        print(f"Error writing cached booking: {e}")

def remove_cached_booking(res_num):
    json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "active_reservations.json")
    if not os.path.exists(json_path):
        return
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            reservations = json.load(f)
    except Exception:
        return
        
    filtered = [r for r in reservations if r.get("reservation_number") != res_num]
    
    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(filtered, f, indent=2)
    except Exception as e:
        print(f"Error removing cached booking: {e}")


def format_reservations_html():
    json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "active_reservations.json")
    if not os.path.exists(json_path):
        return "❌ No active reservations records found."
    
    with open(json_path, "r", encoding="utf-8") as f:
        try:
            reservations = json.load(f)
        except Exception:
            return "❌ Error parsing reservations."
            
    if not reservations:
        return "ℹ️ <b>No active reservations found.</b>"
        
    html_lines = ["📋 <b>Active Ontario Parks Bookings:</b>\n"]
    for idx, r in enumerate(reservations, 1):
        line = (
            f"<b>{idx}. {r['park']}</b>\n"
            f"📅 <b>Date:</b> {r['date']}\n"
            f'🎫 <b>Num:</b> <a href="https://reservations.ontarioparks.ca/account/all-bookings"><b>{r["reservation_number"]}</b></a>\n'
            f"🚗 <b>Vehicle:</b> {r['vehicle']} ({r['occupant']})\n"
            f"───────────────────"
        )
        html_lines.append(line)
        
    return "\n".join(html_lines)

active_approvals = {}

MAIN_REPLY_KEYBOARD = {
    "keyboard": [
        [
            {"text": "📋 List Bookings"},
            {"text": "🌲 Book Daily Permit"}
        ],
        [
            {"text": "❌ Cancel Booking"},
            {"text": "❓ Check Errors"},
            {"text": "🔍 Help"}
        ]
    ],
    "resize_keyboard": True,
    "one_time_keyboard": False
}

def send_telegram_photo(token, chat_id, caption, photo_path, keyboard=None):
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    data = {
        "chat_id": chat_id,
        "caption": caption,
        "parse_mode": "HTML"
    }
    if keyboard:
        data["reply_markup"] = json.dumps(keyboard)
        
    with open(photo_path, "rb") as f:
        files = {"photo": f}
        try:
            res = requests.post(url, data=data, files=files, timeout=20)
            if res.status_code == 200:
                return res.json().get("result", {}).get("message_id")
            else:
                print(f"Error sendPhoto: {res.text}")
        except Exception as e:
            print(f"Error sending photo: {e}")
    return None

def edit_telegram_photo_caption(token, chat_id, message_id, caption):
    url = f"https://api.telegram.org/bot{token}/editMessageCaption"
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "caption": caption,
        "parse_mode": "HTML",
        "reply_markup": json.dumps({"inline_keyboard": []})
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Error editing photo caption: {e}")

def request_approval(step_name, description, screenshot_path):
    token = config["telegram_token"]
    chat_id = config["telegram_chat_id"]
    
    caption = (
        f"⚠️ <b>[Step Approval Required]</b>\n\n"
        f"<b>Step:</b> {step_name}\n"
        f"<b>Summary:</b> {description}\n\n"
        f"Please click below to continue or cancel."
    )
    
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "✅ Approve", "callback_data": "step_approve"},
                {"text": "❌ Deny / Abort", "callback_data": "step_deny"}
            ]
        ]
    }
    
    msg_id = send_telegram_photo(token, chat_id, caption, screenshot_path, keyboard)
    if not msg_id:
        print("Failed to send approval photo to Telegram.")
        return False
        
    event = threading.Event()
    active_approvals[msg_id] = {
        "event": event,
        "status": None
    }
    
    print(f"Waiting for user approval on message {msg_id}...")
    event.wait()
    
    status = active_approvals[msg_id]["status"]
    # Clean up
    active_approvals.pop(msg_id, None)
    
    if status == "approved":
        edit_telegram_photo_caption(token, chat_id, msg_id, f"✅ <b>[Approved]</b>\n<b>Step:</b> {step_name}\nProceeding...")
        return True
    else:
        edit_telegram_photo_caption(token, chat_id, msg_id, f"❌ <b>[Denied / Aborted]</b>\n<b>Step:</b> {step_name}\nBooking halted.")
        return False

def send_telegram_keyboard(token, chat_id, text, keyboard):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": keyboard
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        return res.status_code == 200
    except Exception as e:
        print(f"Error sending keyboard: {e}")
        return False

def edit_telegram_keyboard(token, chat_id, message_id, text, keyboard=None):
    url = f"https://api.telegram.org/bot{token}/editMessageText"
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "HTML"
    }
    if keyboard is not None:
        payload["reply_markup"] = keyboard
    try:
        res = requests.post(url, json=payload, timeout=10)
        return res.status_code == 200
    except Exception as e:
        print(f"Error editing keyboard: {e}")
        return False

def answer_callback_query(token, callback_query_id):
    url = f"https://api.telegram.org/bot{token}/answerCallbackQuery"
    payload = {
        "callback_query_id": callback_query_id
    }
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception:
        pass

def create_calendar_keyboard(park_name, year, month):
    # Calculate next and prev month
    prev_month = month - 1
    prev_year = year
    if prev_month == 0:
        prev_month = 12
        prev_year -= 1
        
    next_month = month + 1
    next_year = year
    if next_month == 13:
        next_month = 1
        next_year += 1
        
    month_name = calendar.month_name[month]
    
    keyboard = {
        "inline_keyboard": [
            # Header Row
            [
                {"text": "◀️", "callback_data": f"cal_month:{park_name}|{prev_year}-{prev_month:02d}"},
                {"text": f"📅 {month_name} {year}", "callback_data": "cal_ignore"},
                {"text": "▶️", "callback_data": f"cal_month:{park_name}|{next_year}-{next_month:02d}"}
            ],
            # Weekdays Row
            [
                {"text": "M", "callback_data": "cal_ignore"},
                {"text": "T", "callback_data": "cal_ignore"},
                {"text": "W", "callback_data": "cal_ignore"},
                {"text": "T", "callback_data": "cal_ignore"},
                {"text": "F", "callback_data": "cal_ignore"},
                {"text": "S", "callback_data": "cal_ignore"},
                {"text": "S", "callback_data": "cal_ignore"}
            ]
        ]
    }
    
    # Days Grid
    cal = calendar.monthcalendar(year, month)
    for week in cal:
        row = []
        for day in week:
            if day == 0:
                row.append({"text": " ", "callback_data": "cal_ignore"})
            else:
                date_str = f"{year}-{month:02d}-{day:02d}"
                row.append({"text": str(day), "callback_data": f"book_btn:{park_name}|{date_str}"})
        keyboard["inline_keyboard"].append(row)
        
    # Navigation/Back Row
    keyboard["inline_keyboard"].append([
        {"text": "🔙 Back to Quick Dates", "callback_data": f"back_to_quick:{park_name}"},
        {"text": "❌ Cancel", "callback_data": "cancel_wizard"}
    ])
    
    return keyboard

def get_quick_dates_keyboard(park_name):
    today_dt = datetime.date.today()
    tomorrow_dt = today_dt + datetime.timedelta(days=1)
    day_after_dt = today_dt + datetime.timedelta(days=2)
    in_3_days_dt = today_dt + datetime.timedelta(days=3)
    
    today_label = f"Today ({today_dt.strftime('%a')})"
    tomorrow_label = f"Tomorrow ({tomorrow_dt.strftime('%a')})"
    day_after_label = f"Day After ({day_after_dt.strftime('%a')})"
    in_3_days_label = f"In 3 Days ({in_3_days_dt.strftime('%a')})"
    
    keyboard = {
        "inline_keyboard": [
            [
                {"text": today_label, "callback_data": f"book_btn:{park_name}|today"},
                {"text": tomorrow_label, "callback_data": f"book_btn:{park_name}|tomorrow"}
            ],
            [
                {"text": day_after_label, "callback_data": f"book_btn:{park_name}|day_after"},
                {"text": in_3_days_label, "callback_data": f"book_btn:{park_name}|{in_3_days_dt.strftime('%Y-%m-%d')}"}
            ],
            [
                {"text": "📅 Select from Calendar", "callback_data": f"show_calendar:{park_name}"},
                {"text": "❌ Cancel Wizard", "callback_data": "cancel_wizard"}
            ]
        ]
    }
    return keyboard

def list_task(for_cancellation=False):
    token = config["telegram_token"]
    chat_id = config["telegram_chat_id"]
    if not acquire_operation("Listing active permits"):
        send_telegram_message(token, chat_id, f"⚠️ Another operation is currently running (<b>{CURRENT_OPERATION}</b>). Please wait for it to complete.")
        return
        
    try:
        # Send status update
        send_telegram_message(token, chat_id, "🔍 Checking active reservations...")
        
        # Run subprocess with timeout of 60 seconds
        res = subprocess.run([sys.executable, "reserve.py", "list"], capture_output=True, text=True, timeout=60)
        if res.returncode == 0:
            json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "active_reservations.json")
            if os.path.exists(json_path):
                with open(json_path, "r", encoding="utf-8") as f:
                    try:
                        reservations = json.load(f)
                    except Exception:
                        reservations = []
            else:
                reservations = []
                
            if not reservations:
                send_telegram_message(token, chat_id, "ℹ️ <b>No active reservations found.</b>")
                return
                
            html_lines = []
            if for_cancellation:
                html_lines.append("❌ <b>Select a booking below to cancel:</b>\n")
            else:
                html_lines.append("📋 <b>Active Ontario Parks Bookings:</b>\n")
                
            inline_keyboard = []
            for idx, r in enumerate(reservations, 1):
                res_num = r["reservation_number"]
                park_name = r["park"]
                date_str = r["date"]
                
                from reserve import fetch_park_alerts
                alerts = fetch_park_alerts(park_name)
                if alerts:
                    alert_lines = []
                    for a in alerts:
                        desc = a["description"].replace("\n", " ")
                        alert_lines.append(f"• <b>{a['type']}:</b> {desc}")
                    alerts_text = "\n".join(alert_lines)
                else:
                    alerts_text = "✅ No active alerts. Safe for swimming! 🏊‍♂️"
                    
                line = (
                    f"<b>{idx}. {park_name}</b>\n"
                    f"📅 <b>Date:</b> {date_str}\n"
                    f'🎫 <b>Num:</b> <a href="https://reservations.ontarioparks.ca/account/all-bookings"><b>{res_num}</b></a>\n'
                    f"🚗 <b>Vehicle:</b> {r['vehicle']} ({r['occupant']})\n"
                    f"🚨 <b>Alerts:</b>\n{alerts_text}\n"
                    f"────────────"
                )
                html_lines.append(line)
                
                # Add inline keyboard button to cancel this booking
                short_park = park_name.replace(" Provincial Park", "")
                inline_keyboard.append([
                    {"text": f"❌ Cancel {short_park} ({date_str})", "callback_data": f"cancel_btn:{res_num}|{short_park}"}
                ])
                
            keyboard = {"inline_keyboard": inline_keyboard}
            send_telegram_keyboard(token, chat_id, "\n".join(html_lines), keyboard)
        else:
            global LAST_ERROR
            LAST_ERROR = f"List Command failed with code {res.returncode}.\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
            reply = f"❌ <b>Failed to list reservations:</b>\n<pre>{escape_html(res.stdout[-300:] or res.stderr[-300:])}</pre>\nUse 'Check Errors' button for details."
            send_telegram_message(token, chat_id, reply)
    except subprocess.TimeoutExpired:
        LAST_ERROR = "Listing bookings operation timed out (60 seconds limit)."
        send_telegram_message(token, chat_id, "❌ <b>Listing bookings operation timed out (60s limit).</b>")
    except Exception as e:
        LAST_ERROR = f"Exception in list task: {str(e)}"
        send_telegram_message(token, chat_id, f"❌ Error: {e}")
    finally:
        release_operation()

def send_progress(step_name, description, screenshot_path):
    token = config["telegram_token"]
    chat_id = config["telegram_chat_id"]
    caption = (
        f"ℹ️ <b>[Booking Progress]</b>\n\n"
        f"<b>Step:</b> {step_name}\n"
        f"<b>Summary:</b> {description}\n"
        f"<b>Status:</b> Page completed successfully ✅"
    )
    send_telegram_photo(token, chat_id, caption, screenshot_path)

def book_task(park, date):
    token = config["telegram_token"]
    chat_id = config["telegram_chat_id"]
    if not acquire_operation(f"Booking {park} for {date}"):
        send_telegram_message(token, chat_id, f"⚠️ Another operation is currently running (<b>{CURRENT_OPERATION}</b>). Please wait for it to complete.")
        return
        
    transaction_time = datetime.datetime.now(datetime.timezone.utc)
    try:
        # Use our Popen runner that parses [PROGRESS] and enforces a 360-second watchdog timeout
        args = [sys.executable, "reserve.py", "book", "--park", park, "--date", date, "--headless", "true", "--skip-email-check"]
        metadata = {"conf_number": "Unknown"}
        success = run_subprocess_with_progress(args, f"Booking {park}", 360, out_metadata=metadata)
        if success:
            conf_num = metadata.get("conf_number", "Unknown")
            if conf_num != "Unknown":
                add_cached_booking(conf_num, park, date)
            send_telegram_message(token, chat_id, f"✅ <b>Booking successfully processed for {park} ({date})!</b>\nWe are now verifying the transaction confirmation email...")
            threading.Thread(target=background_email_monitor, args=("book", transaction_time), daemon=True).start()
    finally:
        release_operation()

def cancel_task(res_num):
    token = config["telegram_token"]
    chat_id = config["telegram_chat_id"]
    if not acquire_operation(f"Cancelling booking {res_num}"):
        send_telegram_message(token, chat_id, f"⚠️ Another operation is currently running (<b>{CURRENT_OPERATION}</b>). Please wait for it to complete.")
        return
        
    transaction_time = datetime.datetime.now(datetime.timezone.utc)
    try:
        send_telegram_message(token, chat_id, f"⏳ Attempting to cancel reservation <a href=\"https://reservations.ontarioparks.ca/account/all-bookings\">{res_num}</a>...")
        
        # Run subprocess with timeout of 90s
        res = subprocess.run([sys.executable, "reserve.py", "cancel", "--reservation", res_num, "--headless", "true", "--skip-email-check"], capture_output=True, text=True, timeout=90)
        if res.returncode == 0:
            remove_cached_booking(res_num)
            threading.Thread(target=background_email_monitor, args=("cancel", transaction_time), daemon=True).start()
        else:
            global LAST_ERROR
            LAST_ERROR = f"Cancel command failed with code {res.returncode}.\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
            reply = f"❌ <b>Cancellation failed:</b>\n<pre>{escape_html(res.stdout[-400:] or res.stderr[-400:])}</pre>\nUse 'Check Errors' button for details."
            send_telegram_message(token, chat_id, reply)
    except subprocess.TimeoutExpired:
        LAST_ERROR = f"Cancellation of {res_num} timed out (90 seconds limit)."
        send_telegram_message(token, chat_id, f"❌ <b>Cancellation operation timed out (90s limit).</b>")
    except Exception as e:
        LAST_ERROR = f"Exception in cancel task: {str(e)}"
        send_telegram_message(token, chat_id, f"❌ Error: {e}")
    finally:
        release_operation()

def handle_command(command_text):
    global CURRENT_OPERATION
    args = command_text.split()
    if not args:
        return
        
    cmd = args[0].lower().split("@")[0] # Strip bot username if present (e.g. /list@AnivaWayBot)
    
    # Check concurrent operations lock
    if cmd in ["/list", "/cancel_list", "/book", "/cancel", "/selftest"]:
        if CURRENT_OPERATION is not None:
            token = config["telegram_token"]
            chat_id = config["telegram_chat_id"]
            send_telegram_message(token, chat_id, f"⚠️ Another operation is currently running (<b>{CURRENT_OPERATION}</b>). Please wait for it to complete.")
            return
    
    if cmd == "/list":
        threading.Thread(target=list_task, args=(False,), daemon=True).start()
        
    elif cmd == "/cancel_list":
        threading.Thread(target=list_task, args=(True,), daemon=True).start()
        
    elif cmd == "/book":
        parks_keyboard = get_recent_parks_keyboard()
        send_telegram_keyboard(config["telegram_token"], config["telegram_chat_id"], "🌲 <b>Ontario Parks Booking Wizard</b>\nSelect a park to book:", parks_keyboard)
        
    elif cmd == "/cancel":
        if len(args) < 2:
            send_telegram_message(config["telegram_token"], config["telegram_chat_id"], "Usage: `/cancel [Reservation Number]`")
            return
        res_num = args[1]
        threading.Thread(target=cancel_task, args=(res_num,), daemon=True).start()
        
    elif cmd == "/selftest":
        threading.Thread(target=run_self_test_flow, daemon=True).start()
        
    elif cmd == "/errors":
        send_telegram_message(config["telegram_token"], config["telegram_chat_id"], f"📋 <b>Last Execution Log/Error:</b>\n\n<pre>{escape_html(LAST_ERROR)}</pre>")
        
    elif cmd in ["/help", "/start"]:
        reply = (
            "🤖 <b>AnivaWay Bot Main Menu:</b>\n\n"
            "Use the reply menu buttons at the bottom to interact with minimal typing:\n"
            "📋 <b>List Bookings</b> - List active reservations.\n"
            "🌲 <b>Book Daily Permit</b> - Start interactive booking.\n"
            "❌ <b>Cancel Booking</b> - Show your bookings with cancel buttons.\n"
            "❓ <b>Check Errors</b> - View details of the last failed action.\n\n"
            "💬 <b>Manual Text Commands:</b>\n"
            "🧪 <code>/selftest</code> - Trigger the booking & cancellation self-test (runs automatically every Monday at 7am).\n"
            "❌ <code>/cancel [Reservation Number]</code> - Directly cancel a specific permit.\n"
            "📋 <code>/list</code> - List bookings.\n"
            "🔍 <code>/help</code> - Show this menu."
        )
        send_telegram_message(config["telegram_token"], config["telegram_chat_id"], reply, MAIN_REPLY_KEYBOARD)

def handle_callback(callback_query):
    global CURRENT_OPERATION
    token = config["telegram_token"]
    chat_id = config["telegram_chat_id"]
    query_id = callback_query["id"]
    message_id = callback_query["message"]["message_id"]
    data = callback_query["data"]
    
    if CURRENT_OPERATION is not None and data not in ["cancel_wizard", "keep_booking", "cal_ignore"]:
        answer_callback_query(token, query_id)
        send_telegram_message(token, chat_id, f"⚠️ Another operation is currently running (<b>{CURRENT_OPERATION}</b>). Please wait for it to complete.")
        return
        
    answer_callback_query(token, query_id)
    
    if data == "cal_ignore":
        return
        
    elif data.startswith("park:"):
        park_name = data.split(":", 1)[1]
        add_recent_park(park_name)
        keyboard = get_quick_dates_keyboard(park_name)
        edit_telegram_keyboard(
            token, chat_id, message_id, 
            f"📅 <b>Select a Date for {park_name}:</b>", 
            keyboard
        )
        
    elif data == "search_park":
        global USER_STATE
        USER_STATE = "awaiting_park_search"
        edit_telegram_keyboard(
            token, chat_id, message_id,
            "🔍 <b>Search for another park:</b>\n\n"
            "Please reply/type the name of the park you want to find (e.g. <i>Pinery</i> or <i>Algonquin</i>).\n\n"
            "Type <code>cancel</code> to exit search."
        )
        
    elif data.startswith("show_calendar:"):
        park_name = data.split(":", 1)[1]
        today_dt = datetime.date.today()
        keyboard = create_calendar_keyboard(park_name, today_dt.year, today_dt.month)
        edit_telegram_keyboard(
            token, chat_id, message_id,
            f"📅 <b>Select a Date for {park_name}:</b>",
            keyboard
        )
        
    elif data.startswith("cal_month:"):
        payload = data.split(":", 1)[1]
        park_name, date_parts = payload.split("|", 1)
        year, month = map(int, date_parts.split("-"))
        keyboard = create_calendar_keyboard(park_name, year, month)
        edit_telegram_keyboard(
            token, chat_id, message_id,
            f"📅 <b>Select a Date for {park_name}:</b>",
            keyboard
        )
        
    elif data.startswith("back_to_quick:"):
        park_name = data.split(":", 1)[1]
        keyboard = get_quick_dates_keyboard(park_name)
        edit_telegram_keyboard(
            token, chat_id, message_id,
            f"📅 <b>Select a Date for {park_name}:</b>",
            keyboard
        )
        
    elif data.startswith("book_btn:"):
        payload = data.split(":", 1)[1]
        park_name, date_val = payload.split("|", 1)
        
        # Format user-friendly date text
        date_label = date_val
        if date_val == "today":
            date_label = "today"
        elif date_val == "tomorrow":
            date_label = "tomorrow"
        elif date_val == "day_after":
            date_label = "day after tomorrow"
            
        # Resolve date_val to YYYY-MM-DD format for duplicate checks
        target_date_str = date_val
        today_dt = datetime.date.today()
        if date_val == "today":
            target_date_str = today_dt.strftime("%Y-%m-%d")
        elif date_val == "tomorrow":
            target_date_str = (today_dt + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        elif date_val == "day_after":
            target_date_str = (today_dt + datetime.timedelta(days=2)).strftime("%Y-%m-%d")
            
        # Check active reservations cache for duplicate date bookings
        json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "active_reservations.json")
        has_same_park = False
        has_diff_park = False
        existing_park = ""
        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    cached_res = json.load(f)
                for r in cached_res:
                    if r.get("date") == target_date_str:
                        existing_park = r.get("park", "")
                        norm_existing = existing_park.lower().replace("provincial park", "").strip()
                        norm_target = park_name.lower().replace("provincial park", "").strip()
                        if norm_existing == norm_target:
                            has_same_park = True
                        else:
                            has_diff_park = True
            except Exception:
                pass
                
        if has_same_park:
            edit_telegram_keyboard(
                token, chat_id, message_id, 
                f"🚫 <b>Booking Blocked:</b> You already have an active permit for <b>{park_name}</b> on <b>{date_label}</b> ({target_date_str}).\n\n"
                f"Duplicate bookings for the same park on the same day are not allowed."
            )
            return
            
        if has_diff_park:
            send_telegram_message(
                token, chat_id, 
                f"⚠️ <b>Notice:</b> You already have an active permit for a different park (<b>{existing_park}</b>) on <b>{date_label}</b> ({target_date_str}).\n\n"
                f"Proceeding with the booking for <b>{park_name}</b> as requested..."
            )
            
        edit_telegram_keyboard(
            token, chat_id, message_id, 
            f"⏳ Attempting to book <b>{park_name}</b> for <b>{date_label}</b>..."
        )
        threading.Thread(target=book_task, args=(park_name, date_val), daemon=True).start()
        
    elif data == "cancel_wizard":
        edit_telegram_keyboard(token, chat_id, message_id, "❌ <i>Booking wizard closed.</i>")
        
    elif data.startswith("cancel_btn:"):
        payload = data.split(":", 1)[1]
        res_num, park_name = payload.split("|", 1)
        confirm_keyboard = {
            "inline_keyboard": [
                [
                    {"text": "✅ Yes, Cancel Booking", "callback_data": f"confirm_cancel:{res_num}"},
                    {"text": "❌ No, Keep Booking", "callback_data": "keep_booking"}
                ]
            ]
        }
        edit_telegram_keyboard(
            token, chat_id, message_id,
            f"⚠️ <b>Are you sure you want to cancel the reservation for {park_name}?</b>\n"
            f"Ticket: <a href=\"https://reservations.ontarioparks.ca/account/all-bookings\">{res_num}</a>\n\n"
            f"<i>This action cannot be undone.</i>",
            confirm_keyboard
        )
        
    elif data.startswith("confirm_cancel:"):
        res_num = data.split(":", 1)[1]
        edit_telegram_keyboard(
            token, chat_id, message_id,
            f"⏳ <b>Initiating automated cancellation wizard...</b>\n"
            f"Reservation: <a href=\"https://reservations.ontarioparks.ca/account/all-bookings\">{res_num}</a>"
        )
        threading.Thread(target=cancel_task, args=(res_num,), daemon=True).start()
        
    elif data == "keep_booking":
        edit_telegram_keyboard(
            token, chat_id, message_id,
            "✅ <i>Booking has been kept and not modified.</i>"
        )

    elif data in ["step_approve", "step_deny"]:
        status = "approved" if data == "step_approve" else "denied"
        if message_id in active_approvals:
            active_approvals[message_id]["status"] = status
            active_approvals[message_id]["event"].set()
        else:
            # Edit caption/text to show expired message
            url = f"https://api.telegram.org/bot{token}/editMessageCaption"
            payload = {
                "chat_id": chat_id,
                "message_id": message_id,
                "caption": "⚠️ <b>Transaction expired or already processed.</b>",
                "parse_mode": "HTML",
                "reply_markup": json.dumps({"inline_keyboard": []})
            }
            try:
                requests.post(url, json=payload, timeout=10)
            except Exception:
                pass

def set_bot_commands(token):
    url = f"https://api.telegram.org/bot{token}/setMyCommands"
    payload = {
        "commands": [
            {"command": "list", "description": "📋 List active permits & cancel them"},
            {"command": "book", "description": "🌲 Book daily permit"},
            {"command": "selftest", "description": "🧪 Run booking & cancellation self-test"},
            {"command": "help", "description": "🔍 Show main menu / help menu"}
        ]
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        print("setMyCommands response:", res.json())
    except Exception as e:
        print("Failed to set bot commands:", e)

def main():
    global config
    config = load_config()
    TOKEN = config["telegram_token"]
    CHAT_ID = config["telegram_chat_id"]
    
    set_bot_commands(TOKEN)
    
    print(f"Starting Telegram Bot command listener for chat ID: {CHAT_ID}...")
    send_telegram_message(TOKEN, CHAT_ID, "🤖 AnivaWay Bot is online and listening for commands!", MAIN_REPLY_KEYBOARD)
    
    # Start background loop for check-in reminders
    def reminder_loop():
        time.sleep(30) # Wait 30 seconds after bot boot
        while True:
            try:
                check_and_notify_checkin_reminders()
            except Exception as e:
                print(f"Error in reminder loop: {e}")
            time.sleep(1800) # Check every 30 minutes
            
    threading.Thread(target=reminder_loop, daemon=True).start()
    threading.Thread(target=selftest_loop, daemon=True).start()
    
    offset = None
    url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
    
    while True:
        try:
            params = {"timeout": 30}
            if offset:
                params["offset"] = offset
            response = requests.get(url, params=params, timeout=35)
            if response.status_code == 200:
                result = response.json().get("result", [])
                for update in result:
                    offset = update["update_id"] + 1
                    
                    # Handle normal commands, reply keyboard buttons, and edited messages
                    message = update.get("message") or update.get("edited_message")
                    if message and str(message["chat"]["id"]) == CHAT_ID:
                        text = message.get("text", "").strip()
                        if text:
                            global USER_STATE
                            # Clear search state if user typed a menu command or slash command
                            is_menu_command = text.startswith("/") or text in [
                                "📋 List Bookings", "🌲 Book Daily Permit", "❌ Cancel Booking", "❓ Check Errors", "🔍 Help", "🔍 Help Menu"
                            ]
                            if is_menu_command:
                                USER_STATE = None
                                
                            if USER_STATE == "awaiting_park_search":
                                if text.lower() == "cancel":
                                    USER_STATE = None
                                    send_telegram_message(TOKEN, CHAT_ID, "❌ <i>Search cancelled.</i>", MAIN_REPLY_KEYBOARD)
                                else:
                                    perform_park_search(text)
                            else:
                                # Map reply keyboard labels to standard commands
                                if text == "📋 List Bookings":
                                    handle_command("/list")
                                elif text == "🌲 Book Daily Permit":
                                    handle_command("/book")
                                elif text == "❌ Cancel Booking":
                                    handle_command("/cancel_list")
                                elif text == "❓ Check Errors":
                                    handle_command("/errors")
                                elif text in ["🔍 Help", "🔍 Help Menu"]:
                                    handle_command("/help")
                                elif text.startswith("/"):
                                    print(f"Received command: {text}")
                                    handle_command(text)
                                else:
                                    print(f"Received unrecognized text: {text}, showing menu")
                                    handle_command("/help")
                            
                    # Handle keyboard selections
                    callback_query = update.get("callback_query")
                    if callback_query:
                        chat_id = str(callback_query["message"]["chat"]["id"])
                        if chat_id == CHAT_ID:
                            handle_callback(callback_query)
                            
        except Exception as e:
            print(f"Error in polling: {e}")
        time.sleep(1)

if __name__ == "__main__":
    main()
