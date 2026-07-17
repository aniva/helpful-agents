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
from reserve import load_config, send_telegram_message, run_booking_flow

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
    
    start_poll = time.time()
    while time.time() - start_poll < 60:
        try:
            mail = imaplib.IMAP4_SSL("imap.gmail.com")
            mail.login(email_user, app_password)
            mail.select("inbox")
            
            search_query = 'OR (FROM "confirmations@camis.com") (SUBJECT "Ontario Parks")'
            status, messages = mail.search(None, search_query)
            if status != "OK":
                status, messages = mail.search(None, '(SUBJECT "Ontario Parks")')
                
            mail_ids = messages[0].split()
            if mail_ids:
                latest_id = mail_ids[-1]
                status, data = mail.fetch(latest_id, "(RFC822)")
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
                    
                    # Ensure email_dt is in UTC
                    if email_dt.tzinfo is None:
                        email_dt = email_dt.replace(tzinfo=datetime.timezone.utc)
                    else:
                        email_dt = email_dt.astimezone(datetime.timezone.utc)
                        
                    # Check if this email is indeed from after our transaction (allowing 60s clock skew)
                    if email_dt >= transaction_time - datetime.timedelta(seconds=60):
                        # Extract summary
                        body = ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                content_type = part.get_content_type()
                                content_disposition = str(part.get("Content-Disposition"))
                                if content_type == "text/plain" and "attachment" not in content_disposition:
                                    body = part.get_payload(decode=True).decode(errors="ignore")
                                    break
                        else:
                            body = msg.get_payload(decode=True).decode(errors="ignore")
                            
                        soup = BeautifulSoup(body, "html.parser")
                        text_content = soup.get_text()
                        
                        # Cleanup text content for summary
                        lines = [line.strip() for line in text_content.split("\n") if line.strip()]
                        summary_lines = []
                        # Look for lines containing keywords
                        for line in lines:
                            if any(k in line.lower() for k in ["confirmation", "cancel", "permit", "vehicle", "plate", "amount", "total", "park", "status"]):
                                if len(line) < 100 and line not in summary_lines:
                                    summary_lines.append(line)
                        
                        summary = ", ".join(summary_lines[:4])
                        if not summary:
                            summary = f"Subject: {subject}"
                            
                        # Determine conclusion
                        conclusion = "all good"
                        lower_subject = subject.lower()
                        lower_body = text_content.lower()
                        
                        if transaction_type == "book":
                            if "cancel" in lower_subject or "cancel" in lower_body:
                                conclusion = "some issues to check (booking resulted in cancellation email?)"
                            elif "warning" in lower_body or "action required" in lower_body or "error" in lower_body:
                                conclusion = "some issues to check (warnings found in email)"
                        elif transaction_type == "cancel":
                            if "confirmation" in lower_subject and "cancel" not in lower_subject and "cancel" not in lower_body:
                                conclusion = "some issues to check (cancellation resulted in confirmation email?)"
                                
                        mail.close()
                        mail.logout()
                        
                        # Local time formatting for output
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
            mail.close()
            mail.logout()
        except Exception as e:
            print(f"IMAP poll error: {e}")
            
        time.sleep(5)
        
    return {
        "status": "not_found",
        "message": "⚠️ Checked for email from Ontario Parks, but no new emails received within 60 seconds.",
        "conclusion": "some issues to check (no email received)"
    }

def verify_email_after_transaction_task(transaction_type, transaction_time):
    # Wait first for email latency, e.g. 5 seconds
    time.sleep(5)
    
    current_config = load_config()
    token = current_config["telegram_token"]
    chat_id = current_config["telegram_chat_id"]
    
    # Check email
    result = check_recent_email_after_transaction(current_config, transaction_type, transaction_time)
    
    if result["status"] == "found":
        msg_text = (
            f"✉️ <b>Ontario Parks Email Verification:</b>\n"
            f"📥 Checked for email from Ontario Parks.\n\n"
            f"📧 <b>Sender:</b> {result['sender']}\n"
            f"📅 <b>Time:</b> {result['time']}\n"
            f"📝 <b>Subject:</b> {result['subject']}\n"
            f"🔍 <b>Summary:</b> {result['summary']}\n\n"
            f"🤖 <b>Conclusion:</b> <b>{result['conclusion']}</b>"
        )
    elif result["status"] == "not_found":
        msg_text = (
            f"✉️ <b>Ontario Parks Email Verification:</b>\n"
            f"📥 Checked for email from Ontario Parks.\n\n"
            f"{result['message']}\n\n"
            f"🤖 <b>Conclusion:</b> <b>{result['conclusion']}</b>"
        )
    else:
        # skipped
        msg_text = result["message"]
        
    send_telegram_message(token, chat_id, msg_text)

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
        {"text": "🔙 Back to Quick Dates", "callback_data": f"back_to_quick:{park_name}"}
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
    try:
        token = config["telegram_token"]
        chat_id = config["telegram_chat_id"]
        
        # Send status update
        send_telegram_message(token, chat_id, "🔍 Checking active reservations...")
        
        # Run subprocess
        res = subprocess.run([sys.executable, "reserve.py", "list"], capture_output=True, text=True)
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
            reply = f"❌ <b>Failed to list reservations:</b>\n<pre>{res.stdout[-300:] or res.stderr[-300:]}</pre>"
            send_telegram_message(token, chat_id, reply)
    except Exception as e:
        send_telegram_message(config["telegram_token"], config["telegram_chat_id"], f"❌ Error: {e}")

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
    try:
        transaction_time = datetime.datetime.now(datetime.timezone.utc)
        success = run_booking_flow(
            config,
            target_park_override=park,
            target_date_override=date,
            is_headless=True,
            request_approval_callback=None,
            progress_callback=send_progress
        )
        if success:
            reply = "✅ <b>Booking process completed successfully!</b>"
            threading.Thread(target=verify_email_after_transaction_task, args=("book", transaction_time), daemon=True).start()
        else:
            reply = f"❌ <b>Booking aborted or failed for {park} ({date}).</b>"
            
        send_telegram_message(config["telegram_token"], config["telegram_chat_id"], reply)
    except Exception as e:
        send_telegram_message(config["telegram_token"], config["telegram_chat_id"], f"❌ <b>Booking failed with error:</b> {e}")

def cancel_task(res_num):
    try:
        send_telegram_message(config["telegram_token"], config["telegram_chat_id"], f"⏳ Attempting to cancel reservation <a href=\"https://reservations.ontarioparks.ca/account/all-bookings\">{res_num}</a>...")
        
        transaction_time = datetime.datetime.now(datetime.timezone.utc)
        # Run subprocess
        res = subprocess.run([sys.executable, "reserve.py", "cancel", "--reservation", res_num, "--headless", "true"], capture_output=True, text=True)
        if res.returncode == 0:
            reply = f"✅ <b>Reservation <a href=\"https://reservations.ontarioparks.ca/account/all-bookings\">{res_num}</a> has been successfully cancelled!</b>"
            threading.Thread(target=verify_email_after_transaction_task, args=("cancel", transaction_time), daemon=True).start()
        else:
            reply = f"❌ <b>Cancellation failed:</b>\n<pre>{res.stdout[-400:] or res.stderr[-400:]}</pre>"
            
        send_telegram_message(config["telegram_token"], config["telegram_chat_id"], reply)
    except Exception as e:
        send_telegram_message(config["telegram_token"], config["telegram_chat_id"], f"❌ Error: {e}")

def handle_command(command_text):
    args = command_text.split()
    if not args:
        return
        
    cmd = args[0].lower().split("@")[0] # Strip bot username if present (e.g. /list@AnivaWayBot)
    
    if cmd == "/list":
        threading.Thread(target=list_task, args=(False,), daemon=True).start()
        
    elif cmd == "/cancel_list":
        threading.Thread(target=list_task, args=(True,), daemon=True).start()
        
    elif cmd == "/book":
        parks_keyboard = {
            "inline_keyboard": [
                [
                    {"text": "🌲 Sibbald Point", "callback_data": "park:Sibbald Point"},
                    {"text": "🌲 Presqu'ile", "callback_data": "park:Presqu'ile"}
                ],
                [
                    {"text": "🌲 Wasaga Beach (Area 6)", "callback_data": "park:Wasaga Beach 6"}
                ]
            ]
        }
        send_telegram_keyboard(config["telegram_token"], config["telegram_chat_id"], "🌲 <b>Ontario Parks Booking Wizard</b>\nSelect a park to book:", parks_keyboard)
        
    elif cmd == "/cancel":
        if len(args) < 2:
            send_telegram_message(config["telegram_token"], config["telegram_chat_id"], "Usage: `/cancel [Reservation Number]`")
            return
        res_num = args[1]
        threading.Thread(target=cancel_task, args=(res_num,), daemon=True).start()
        
    elif cmd in ["/help", "/start"]:
        reply = (
            "🤖 <b>AnivaWay Bot Main Menu:</b>\n\n"
            "Use the buttons below to interact with the bot with minimal typing:\n"
            "📋 <b>List Bookings</b> - Shows your active daily permits and lets you cancel them.\n"
            "🌲 <b>Book Daily Permit</b> - Interactive booking wizard for your favorite kiting spots.\n"
            "❌ <b>Cancel Booking</b> - Display your bookings to cancel them.\n"
            "🔍 <b>Help</b> - Show this help menu."
        )
        send_telegram_message(config["telegram_token"], config["telegram_chat_id"], reply, MAIN_REPLY_KEYBOARD)

def handle_callback(callback_query):
    token = config["telegram_token"]
    chat_id = config["telegram_chat_id"]
    query_id = callback_query["id"]
    message_id = callback_query["message"]["message_id"]
    data = callback_query["data"]
    
    answer_callback_query(token, query_id)
    
    if data == "cal_ignore":
        return
        
    elif data.startswith("park:"):
        park_name = data.split(":", 1)[1]
        keyboard = get_quick_dates_keyboard(park_name)
        edit_telegram_keyboard(
            token, chat_id, message_id, 
            f"📅 <b>Select a Date for {park_name}:</b>", 
            keyboard
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
    send_telegram_message(TOKEN, CHAT_ID, "🤖 AnivaWay Bot is online and listening for commands!")
    
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
                    
                    # Handle normal commands and reply keyboard buttons
                    message = update.get("message")
                    if message and str(message["chat"]["id"]) == CHAT_ID:
                        text = message.get("text", "").strip()
                        if text:
                            # Map reply keyboard labels to standard commands
                            if text == "📋 List Bookings":
                                handle_command("/list")
                            elif text == "🌲 Book Daily Permit":
                                handle_command("/book")
                            elif text == "❌ Cancel Booking":
                                handle_command("/cancel_list")
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
