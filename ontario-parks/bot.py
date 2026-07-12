import subprocess
import time
import requests
import json
import os
import sys

# Add current dir to path to import reserve
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from reserve import load_config, send_telegram_message

def handle_command(command_text):
    args = command_text.split()
    if not args:
        return None
        
    cmd = args[0].lower().split("@")[0] # Strip bot username if present (e.g. /list@AnivaWayBot)
    
    if cmd == "/list":
        send_telegram_message(config["telegram_token"], config["telegram_chat_id"], "🔍 Checking active reservations...")
        res = subprocess.run([sys.executable, "reserve.py", "list"], capture_output=True, text=True)
        return res.stdout
        
    elif cmd == "/book":
        if len(args) < 2:
            return "Usage: /book [Park Name] [Date (today|tomorrow|day_after|YYYY-MM-DD)]\nExample: /book Sibbald Point tomorrow"
        
        # Determine if last argument is the date
        last_arg = args[-1].lower()
        if last_arg in ["today", "tomorrow", "day_after"] or len(last_arg.split("-")) == 3:
            park = " ".join(args[1:-1])
            date = last_arg
        else:
            park = " ".join(args[1:])
            date = "tomorrow"
            
        send_telegram_message(config["telegram_token"], config["telegram_chat_id"], f"⏳ Attempting to book {park} for {date}...")
        res = subprocess.run([sys.executable, "reserve.py", "book", "--park", park, "--date", date, "--headless", "true"], capture_output=True, text=True)
        return res.stdout
        
    elif cmd == "/cancel":
        if len(args) < 2:
            return "Usage: /cancel [Reservation Number]\nExample: /cancel INOP26-7139739B1"
        res_num = args[1]
        send_telegram_message(config["telegram_token"], config["telegram_chat_id"], f"⏳ Attempting to cancel reservation {res_num}...")
        res = subprocess.run([sys.executable, "reserve.py", "cancel", "--reservation", res_num, "--headless", "true"], capture_output=True, text=True)
        return res.stdout
        
    return None

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
                            reply = handle_command(text)
                            if reply:
                                # Format output nicely in Telegram
                                send_telegram_message(TOKEN, CHAT_ID, f"<pre>{reply}</pre>")
        except Exception as e:
            print(f"Error in polling: {e}")
        time.sleep(1)

if __name__ == "__main__":
    main()
