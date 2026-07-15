import subprocess
import time
import requests
import json
import os
import sys
import threading
import datetime
import calendar

# Add current dir to path to import reserve
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from reserve import load_config, send_telegram_message

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

def list_task():
    try:
        # Send status update
        send_telegram_message(config["telegram_token"], config["telegram_chat_id"], "🔍 Checking active reservations...")
        
        # Run subprocess
        res = subprocess.run([sys.executable, "reserve.py", "list"], capture_output=True, text=True)
        if res.returncode == 0:
            reply = format_reservations_html()
        else:
            reply = f"❌ <b>Failed to list reservations:</b>\n<pre>{res.stdout[-300:] or res.stderr[-300:]}</pre>"
        
        send_telegram_message(config["telegram_token"], config["telegram_chat_id"], reply)
    except Exception as e:
        send_telegram_message(config["telegram_token"], config["telegram_chat_id"], f"❌ Error: {e}")

def book_task(park, date):
    try:
        # Run subprocess
        res = subprocess.run([sys.executable, "reserve.py", "book", "--park", park, "--date", date, "--headless", "true"], capture_output=True, text=True)
        if res.returncode == 0:
            reply = "✅ <b>Booking process completed successfully!</b>"
        else:
            reply = f"❌ <b>Booking failed for {park} ({date}):</b>\n<pre>{res.stdout[-400:] or res.stderr[-400:]}</pre>"
            
        send_telegram_message(config["telegram_token"], config["telegram_chat_id"], reply)
    except Exception as e:
        send_telegram_message(config["telegram_token"], config["telegram_chat_id"], f"❌ Error: {e}")

def cancel_task(res_num):
    try:
        send_telegram_message(config["telegram_token"], config["telegram_chat_id"], f"⏳ Attempting to cancel reservation <code>{res_num}</code>...")
        
        # Run subprocess
        res = subprocess.run([sys.executable, "reserve.py", "cancel", "--reservation", res_num, "--headless", "true"], capture_output=True, text=True)
        if res.returncode == 0:
            reply = f"✅ <b>Reservation <code>{res_num}</code> has been successfully cancelled!</b>"
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
        threading.Thread(target=list_task, daemon=True).start()
        
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
            "🤖 <b>AnivaWay Bot Help Menu:</b>\n\n"
            "📋 <b>Commands:</b>\n"
            "• `/list` - List all active reservations.\n"
            "• `/book` - Start interactive day-use booking wizard.\n"
            "• `/cancel [Reservation ID]` - Cancel a specific booking.\n"
            "  <i>Example:</i> <code>/cancel INOP26-7139739B1</code>"
        )
        send_telegram_message(config["telegram_token"], config["telegram_chat_id"], reply)

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

def main():
    global config
    config = load_config()
    TOKEN = config["telegram_token"]
    CHAT_ID = config["telegram_chat_id"]
    
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
                    
                    # Handle normal commands
                    message = update.get("message")
                    if message and str(message["chat"]["id"]) == CHAT_ID:
                        text = message.get("text", "")
                        if text.startswith("/"):
                            print(f"Received command: {text}")
                            handle_command(text)
                            
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
