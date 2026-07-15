import subprocess
import time
import requests
import json
import os
import sys
import threading

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
            f"🎫 <b>Num:</b> <a href='https://reservations.ontarioparks.ca/account/all-bookings'><code>{r['reservation_number']}</code></a>\n"
            f"🚗 <b>Vehicle:</b> {r['vehicle']} ({r['occupant']})\n"
            f"───────────────────"
        )
        html_lines.append(line)
        
    return "\n".join(html_lines)

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
        send_telegram_message(config["telegram_token"], config["telegram_chat_id"], f"⏳ Attempting to book <b>{park}</b> for <b>{date}</b>...")
        
        # Run subprocess
        res = subprocess.run([sys.executable, "reserve.py", "book", "--park", park, "--date", date, "--headless", "true"], capture_output=True, text=True)
        if res.returncode == 0:
            reply = "✅ <b>Booking process completed successfully!</b>"
        else:
            reply = f"❌ <b>Booking failed:</b>\n<pre>{res.stdout[-400:] or res.stderr[-400:]}</pre>"
            
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
        if len(args) < 2:
            send_telegram_message(config["telegram_token"], config["telegram_chat_id"], "Usage: `/book [Park Name] [Date]`")
            return
        
        # Determine if last argument is the date
        last_arg = args[-1].lower()
        if last_arg in ["today", "tomorrow", "day_after"] or len(last_arg.split("-")) == 3:
            park = " ".join(args[1:-1])
            date = last_arg
        else:
            park = " ".join(args[1:])
            date = "tomorrow"
            
        threading.Thread(target=book_task, args=(park, date), daemon=True).start()
        
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
            "• `/book [Park] [Date]` - Book a day-use permit (defaults to tomorrow).\n"
            "  <i>Example:</i> <code>/book Sibbald Point tomorrow</code>\n"
            "• `/cancel [Reservation ID]` - Cancel a specific booking.\n"
            "  <i>Example:</i> <code>/cancel INOP26-7139739B1</code>"
        )
        send_telegram_message(config["telegram_token"], config["telegram_chat_id"], reply)

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
                    message = update.get("message")
                    if message and str(message["chat"]["id"]) == CHAT_ID:
                        text = message.get("text", "")
                        if text.startswith("/"):
                            print(f"Received command: {text}")
                            handle_command(text)
        except Exception as e:
            print(f"Error in polling: {e}")
        time.sleep(1)

if __name__ == "__main__":
    main()
