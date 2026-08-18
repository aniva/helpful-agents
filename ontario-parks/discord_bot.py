import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import subprocess
import os
import sys
import json
import datetime
import calendar
import threading
import time

# Add current dir to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from reserve import (
    load_config,
    clean_park_name,
    check_recent_email_after_transaction,
    PARKS,
    fetch_weather_forecast,
    fetch_park_alerts
)

# Global variables and locks
config = load_config()
TOKEN = config.get("discord_token")
CHANNEL_ID = config.get("discord_channel_id")
ALLOWED_USER_IDS = [
    uid.strip() for uid in str(config.get("discord_allowed_user_ids", "")).split(",") if uid.strip()
]

op_lock = threading.Lock()
CURRENT_OPERATION = None
LAST_ERROR = "No errors recorded."

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

def is_authorized(user_id):
    if not ALLOWED_USER_IDS:
        return True # Default to open if not explicitly configured
    return str(user_id) in ALLOWED_USER_IDS

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

# Active reservations cache helpers
def get_active_reservations():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "active_reservations.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def add_cached_booking(park_name, date_str, conf_num):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "active_reservations.json")
    bookings = get_active_reservations()
    # Check if already exists
    for b in bookings:
        if b.get("conf_number") == conf_num:
            return
    bookings.append({
        "park_name": park_name,
        "date_str": date_str,
        "conf_number": conf_num,
        "created_at": datetime.datetime.now().isoformat()
    })
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(bookings, f, indent=4)
    except Exception:
        pass

def remove_cached_booking(conf_num):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "active_reservations.json")
    bookings = get_active_reservations()
    bookings = [b for b in bookings if b.get("conf_number") != conf_num]
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(bookings, f, indent=4)
    except Exception:
        pass

def get_recent_parks():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "recent_parks.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                recent = json.load(f)
                cleaned = [clean_park_name(p) for p in recent if clean_park_name(p)]
                if cleaned:
                    return cleaned
        except Exception:
            pass
    return ["Sibbald Point", "Wasaga Beach", "Presqu'ile", "Sandbanks"]

# -------------------------------------------------------------
# Zero-Typing UI Views (Select Menus and Action Buttons)
# -------------------------------------------------------------

class ParkSelectDropdown(discord.ui.Select):
    def __init__(self):
        parks_list = [
            ("Sibbald Point", "Lake Simcoe - Kiting & Beach", "🏖️"),
            ("Wasaga Beach", "Georgian Bay - Beach Area 6", "🌊"),
            ("Presqu'ile", "Lake Ontario - Kiting & Nature", "🦅"),
            ("Sandbanks", "Lake Ontario - Dunes & Beach", "🏜️"),
            ("Long Point", "Lake Erie - Sandy Spit & Kiting", "🛶"),
            ("Turkey Point", "Lake Erie - Warm Shallow Bay", "🦃"),
            ("Craigleith", "Georgian Bay - Shale Beach", "🪨")
        ]
        options = [
            discord.SelectOption(label=name, description=desc, emoji=emoji, value=name)
            for name, desc, emoji in parks_list
        ]
        super().__init__(
            placeholder="🌲 Choose a park to start booking...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="dropdown_select_park"
        )

    async def callback(self, interaction: discord.Interaction):
        if not is_authorized(interaction.user.id):
            await interaction.response.send_message("⛔ You are not authorized to use this bot.", ephemeral=True)
            return

        selected_park = self.values[0]
        view = BookingDateView(selected_park)
        embed = discord.Embed(
            title=f"📅 Select Reservation Date for {selected_park}",
            description="Choose one of the quick dates below to proceed with booking:",
            color=0x2b82d9
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class ControlDashboardView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ParkSelectDropdown())

    @discord.ui.button(label="List Bookings", style=discord.ButtonStyle.primary, emoji="📋", custom_id="dash_btn_list", row=1)
    async def btn_list(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_authorized(interaction.user.id):
            await interaction.response.send_message("⛔ Unauthorized.", ephemeral=True)
            return
        await handle_list_command(interaction)

    @discord.ui.button(label="Book Daily Permit", style=discord.ButtonStyle.success, emoji="🌲", custom_id="dash_btn_book", row=1)
    async def btn_book(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_authorized(interaction.user.id):
            await interaction.response.send_message("⛔ Unauthorized.", ephemeral=True)
            return
        view = ParkButtonsView()
        embed = discord.Embed(
            title="🌲 Ontario Parks Booking Wizard",
            description="Select a provincial park below to begin:",
            color=0x2b82d9
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="Cancel Booking", style=discord.ButtonStyle.danger, emoji="❌", custom_id="dash_btn_cancel", row=1)
    async def btn_cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_authorized(interaction.user.id):
            await interaction.response.send_message("⛔ Unauthorized.", ephemeral=True)
            return
        await handle_cancel_list_command(interaction)

    @discord.ui.button(label="Run Self-Test", style=discord.ButtonStyle.secondary, emoji="🧪", custom_id="dash_btn_selftest", row=2)
    async def btn_selftest(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_authorized(interaction.user.id):
            await interaction.response.send_message("⛔ Unauthorized.", ephemeral=True)
            return
        await handle_selftest_command(interaction)

    @discord.ui.button(label="Check Errors", style=discord.ButtonStyle.secondary, emoji="❓", custom_id="dash_btn_errors", row=2)
    async def btn_errors(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_authorized(interaction.user.id):
            await interaction.response.send_message("⛔ Unauthorized.", ephemeral=True)
            return
        embed = discord.Embed(
            title="📋 Last Execution Error / Log",
            description=f"```\n{LAST_ERROR[:1900]}\n```",
            color=0xe74c3c if "error" in LAST_ERROR.lower() or "fail" in LAST_ERROR.lower() else 0x95a5a6
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Refresh Menu", style=discord.ButtonStyle.secondary, emoji="🔄", custom_id="dash_btn_refresh", row=2)
    async def btn_refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_authorized(interaction.user.id):
            await interaction.response.send_message("⛔ Unauthorized.", ephemeral=True)
            return
        embed = create_dashboard_embed()
        await interaction.response.edit_message(embed=embed, view=ControlDashboardView())

class ParkButtonsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        recent = get_recent_parks()
        for park in recent:
            btn = discord.ui.Button(label=park, style=discord.ButtonStyle.primary, emoji="🌲", custom_id=f"park_btn_{park}")
            btn.callback = self.make_park_callback(park)
            self.add_item(btn)

    def make_park_callback(self, park_name):
        async def park_callback(interaction: discord.Interaction):
            view = BookingDateView(park_name)
            embed = discord.Embed(
                title=f"📅 Select Reservation Date for {park_name}",
                description="Choose one of the quick dates below:",
                color=0x2b82d9
            )
            await interaction.response.edit_message(embed=embed, view=view)
        return park_callback

class BookingDateView(discord.ui.View):
    def __init__(self, park_name):
        super().__init__(timeout=180)
        self.park_name = park_name
        
        today = datetime.date.today()
        dates = [
            ("Today", today.strftime("%Y-%m-%d")),
            ("Tomorrow", (today + datetime.timedelta(days=1)).strftime("%Y-%m-%d")),
            ("Day After", (today + datetime.timedelta(days=2)).strftime("%Y-%m-%d")),
        ]
        
        # Add next 4 upcoming days
        for offset in range(3, 7):
            d = today + datetime.timedelta(days=offset)
            label = d.strftime("%a (%b %d)")
            dates.append((label, d.strftime("%Y-%m-%d")))
            
        for label, val in dates[:6]:
            btn = discord.ui.Button(label=label, style=discord.ButtonStyle.secondary, custom_id=f"date_{val}")
            btn.callback = self.make_date_callback(val)
            self.add_item(btn)

    def make_date_callback(self, date_str):
        async def date_callback(interaction: discord.Interaction):
            await launch_booking_flow(interaction, self.park_name, date_str)
        return date_callback

class CancelConfirmationView(discord.ui.View):
    def __init__(self, reservations):
        super().__init__(timeout=180)
        for r in reservations[:5]:
            conf_num = r.get("reservation_number") or r.get("conf_number") or ""
            park = r.get("park") or r.get("park_name") or "Park"
            date_str = r.get("date") or r.get("date_str") or ""
            short_park = park.replace(" Provincial Park", "")
            label = f"Cancel {short_park} ({date_str})"[:80]
            btn = discord.ui.Button(label=label, style=discord.ButtonStyle.danger, emoji="❌", custom_id=f"cancel_{conf_num}")
            btn.callback = self.make_cancel_callback(conf_num, park, date_str)
            self.add_item(btn)

    def make_cancel_callback(self, conf_num, park_name, date_str):
        async def cancel_callback(interaction: discord.Interaction):
            await launch_cancellation_flow(interaction, conf_num, park_name, date_str)
        return cancel_callback

# -------------------------------------------------------------
# Dashboard Embed Generator
# -------------------------------------------------------------

def create_dashboard_embed():
    embed = discord.Embed(
        title="🌲 Ontario Parks Reservation Assistant",
        description=(
            "Welcome! Use the pull-out dropdown menu or quick buttons below to control your Ontario Parks permits.\n\n"
            "• **Quick Book**: Select any park from the dropdown menu.\n"
            "• **List Permits**: View active permits, vehicle plates, and park swimming alerts.\n"
            "• **Cancel**: Cancel an active permit directly with one click.\n"
            "• **Self-Test**: Test the end-to-end booking, cancellation, and IMAP email flow."
        ),
        color=0x2ecc71
    )
    embed.set_footer(text="Ontario Parks Daemon • Live & Ready")
    embed.timestamp = datetime.datetime.now()
    return embed

# -------------------------------------------------------------
# Background Subprocess & Progress Updates
# -------------------------------------------------------------

async def launch_booking_flow(interaction: discord.Interaction, park_name, date_str):
    if not acquire_operation(f"Booking {park_name}"):
        await interaction.response.send_message(
            f"⚠️ Another operation is currently running (<b>{CURRENT_OPERATION}</b>). Please wait for it to complete.",
            ephemeral=True
        )
        return

    embed = discord.Embed(
        title=f"🌲 Booking in Progress: {park_name}",
        description=f"📅 **Date:** `{date_str}`\n⏳ Initializing browser session...",
        color=0xf39c12
    )
    await interaction.response.send_message(embed=embed, ephemeral=False)
    msg = await interaction.original_response()

    loop = asyncio.get_running_loop()
    
    def run_process():
        global LAST_ERROR
        args = [
            sys.executable,
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "reserve.py"),
            "book",
            "--park", park_name,
            "--date", date_str,
            "--headless", "true"
        ]
        
        proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        conf_number = None
        current_step = "Starting"
        current_desc = "Initializing..."
        current_image = None
        
        for line in iter(proc.stdout.readline, ""):
            line_str = line.strip()
            print(f"[Subprocess] {line_str}")
            if "[PROGRESS]" in line_str:
                try:
                    parts = line_str.split("[PROGRESS]")[1].strip().split("|")
                    for p in parts:
                        p = p.strip()
                        if p.startswith("Step:"):
                            current_step = p.replace("Step:", "").strip()
                        elif p.startswith("Desc:"):
                            current_desc = p.replace("Desc:", "").strip()
                        elif p.startswith("Image:"):
                            current_image = p.replace("Image:", "").strip()
                    
                    # Update Discord embed
                    step_embed = discord.Embed(
                        title=f"🌲 Booking {park_name}: {current_step}",
                        description=f"📅 **Date:** `{date_str}`\n📝 **Status:** {current_desc}",
                        color=0x3498db
                    )
                    
                    file_to_send = None
                    if current_image and os.path.exists(current_image):
                        file_to_send = discord.File(current_image, filename="progress.png")
                        step_embed.set_image(url="attachment://progress.png")
                        
                    asyncio.run_coroutine_threadsafe(
                        msg.edit(embed=step_embed, attachments=[file_to_send] if file_to_send else []),
                        loop
                    )
                except Exception as ex:
                    print(f"Error parsing progress tag: {ex}")
                    
            if "CONFIRMATION_NUMBER=" in line_str:
                conf_number = line_str.split("CONFIRMATION_NUMBER=")[1].strip()
                
        proc.stdout.close()
        stderr_output = proc.stderr.read()
        proc.stderr.close()
        proc.wait()
        
        success = (proc.returncode == 0) and (conf_number is not None)
        if not success:
            LAST_ERROR = f"Booking failed with returncode {proc.returncode}.\nSTDERR:\n{stderr_output}"
            
        return success, conf_number, stderr_output

    try:
        success, conf_number, stderr_out = await loop.run_in_executor(None, run_process)
        if success:
            add_cached_booking(park_name, date_str, conf_number)
            success_embed = discord.Embed(
                title="✅ Booking Confirmed Successfully!",
                description=(
                    f"🌲 **Park:** {park_name}\n"
                    f"📅 **Date:** `{date_str}`\n"
                    f"🔑 **Confirmation Number:** `{conf_number}`\n\n"
                    f"✉️ *Checking inbox for transaction receipt...*"
                ),
                color=0x2ecc71
            )
            await msg.edit(embed=success_embed, attachments=[])
        else:
            error_embed = discord.Embed(
                title="❌ Booking Failed",
                description=f"Automated booking for **{park_name}** on `{date_str}` could not be completed.\nUse `❓ Check Errors` for details.",
                color=0xe74c3c
            )
            await msg.edit(embed=error_embed, attachments=[])
    finally:
        release_operation()

async def launch_cancellation_flow(interaction: discord.Interaction, conf_num, park_name, date_str):
    if not acquire_operation(f"Cancelling {conf_num}"):
        await interaction.response.send_message(
            f"⚠️ Another operation is currently running (<b>{CURRENT_OPERATION}</b>).",
            ephemeral=True
        )
        return

    embed = discord.Embed(
        title=f"❌ Cancelling Reservation: {conf_num}",
        description=f"🌲 **Park:** {park_name}\n📅 **Date:** `{date_str}`\n⏳ Submitting cancellation...",
        color=0xe67e22
    )
    await interaction.response.send_message(embed=embed, ephemeral=False)
    msg = await interaction.original_response()

    loop = asyncio.get_running_loop()
    
    def run_cancel():
        global LAST_ERROR
        args = [
            sys.executable,
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "reserve.py"),
            "cancel",
            "--reservation", conf_num,
            "--headless", "true"
        ]
        res = subprocess.run(args, capture_output=True, text=True, timeout=120)
        if res.returncode != 0:
            LAST_ERROR = f"Cancellation failed with code {res.returncode}.\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        return res.returncode == 0

    try:
        success = await loop.run_in_executor(None, run_cancel)
        if success:
            remove_cached_booking(conf_num)
            done_embed = discord.Embed(
                title="✅ Reservation Cancelled",
                description=f"Reservation **{conf_num}** ({park_name}) has been cancelled successfully.",
                color=0x2ecc71
            )
            await msg.edit(embed=done_embed)
        else:
            fail_embed = discord.Embed(
                title="⚠️ Cancellation Issue",
                description=f"Automated cancellation for **{conf_num}** failed.\nPlease check errors or cancel manually on ontarioparks.ca.",
                color=0xe74c3c
            )
            await msg.edit(embed=fail_embed)
    finally:
        release_operation()

# -------------------------------------------------------------
# Command Handlers
# -------------------------------------------------------------

async def handle_list_command(interaction: discord.Interaction):
    if not acquire_operation("Checking Active Reservations"):
        busy_embed = discord.Embed(
            title="⚠️ Operation In Progress",
            description=f"Another operation is currently running (**{CURRENT_OPERATION}**).\nPlease wait for it to complete.",
            color=0xf1c40f
        )
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=busy_embed, ephemeral=True)
        else:
            await interaction.followup.send(embed=busy_embed, ephemeral=True)
        return

    try:
        # Send immediate visible status card (matching Telegram behavior)
        status_embed = discord.Embed(
            title="🔍 Checking Active Reservations...",
            description="⏳ Logging into Ontario Parks account to fetch live bookings... Please wait.",
            color=0xf39c12
        )
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=status_embed, ephemeral=False)
            msg = await interaction.original_response()
        else:
            msg = await interaction.followup.send(embed=status_embed, ephemeral=False)

        loop = asyncio.get_running_loop()
        
        def run_live_list():
            try:
                res = subprocess.run(
                    [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "reserve.py"), "list", "--headless", "true"],
                    capture_output=True, text=True, timeout=60
                )
                return res.returncode == 0
            except Exception as ex:
                print(f"Error running live list: {ex}")
                return False

        await loop.run_in_executor(None, run_live_list)
        
        bookings = get_active_reservations()
        if not bookings:
            empty_embed = discord.Embed(
                title="ℹ️ No Active Reservations Found",
                description="You currently have no active vehicle permits booked on your Ontario Parks account.\nUse the menu to book a permit!",
                color=0x95a5a6
            )
            await msg.edit(embed=empty_embed, view=None)
            return

        desc_lines = []
        for idx, b in enumerate(bookings, 1):
            park = b.get("park") or b.get("park_name") or "Unknown Park"
            date_str = b.get("date") or b.get("date_str") or "Unknown Date"
            conf_num = b.get("reservation_number") or b.get("conf_number") or "N/A"
            vehicle = b.get("vehicle", "")
            occupant = b.get("occupant", "")
            
            alerts = fetch_park_alerts(park)
            if alerts:
                alert_lines = [f"• **{a['type']}:** {a['description'].replace(chr(10), ' ')}" for a in alerts]
                alerts_text = "\n".join(alert_lines)
            else:
                alerts_text = "✅ No active alerts. Safe for swimming! 🏊‍♂️"
                
            vehicle_str = f"\n🚗 **Vehicle:** `{vehicle}` ({occupant})" if vehicle else ""
            desc_lines.append(
                f"**{idx}. {park}**\n"
                f"📅 **Date:** `{date_str}`\n"
                f"🔑 **Confirmation #:** `{conf_num}`{vehicle_str}\n"
                f"🚨 **Alerts:**\n{alerts_text}\n"
                f"────────────"
            )

        res_embed = discord.Embed(
            title="📋 Active Ontario Parks Bookings",
            description="\n".join(desc_lines),
            color=0x2ecc71
        )
        view = CancelConfirmationView(bookings)
        await msg.edit(embed=res_embed, view=view)
    finally:
        release_operation()

async def handle_cancel_list_command(interaction: discord.Interaction):
    if not acquire_operation("Fetching Reservations to Cancel"):
        busy_embed = discord.Embed(
            title="⚠️ Operation In Progress",
            description=f"Another operation is currently running (**{CURRENT_OPERATION}**).\nPlease wait for it to complete.",
            color=0xf1c40f
        )
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=busy_embed, ephemeral=True)
        else:
            await interaction.followup.send(embed=busy_embed, ephemeral=True)
        return

    try:
        # Send immediate visible status card (matching Telegram behavior)
        status_embed = discord.Embed(
            title="🔍 Fetching Reservations...",
            description="⏳ Checking active permits to cancel... Please wait.",
            color=0xf39c12
        )
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=status_embed, ephemeral=False)
            msg = await interaction.original_response()
        else:
            msg = await interaction.followup.send(embed=status_embed, ephemeral=False)

        loop = asyncio.get_running_loop()
        
        def run_live_list():
            try:
                res = subprocess.run(
                    [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "reserve.py"), "list", "--headless", "true"],
                    capture_output=True, text=True, timeout=60
                )
                return res.returncode == 0
            except Exception:
                return False

        await loop.run_in_executor(None, run_live_list)
        
        bookings = get_active_reservations()
        if not bookings:
            empty_embed = discord.Embed(
                title="❌ Cancel Booking",
                description="No active bookings available to cancel.",
                color=0x95a5a6
            )
            await msg.edit(embed=empty_embed, view=None)
            return

        cancel_embed = discord.Embed(
            title="❌ Select a Reservation to Cancel",
            description="Click one of the buttons below to cancel that permit directly:",
            color=0xe74c3c
        )
        view = CancelConfirmationView(bookings)
        await msg.edit(embed=cancel_embed, view=view)
    finally:
        release_operation()

def poll_email_verification_for_discord_selftest(transaction_type, transaction_time, max_attempts=6, delay=20):
    for attempt in range(max_attempts):
        result = check_recent_email_after_transaction(load_config(), transaction_type, transaction_time)
        if result.get("status") == "found":
            return result
        time.sleep(delay)
    return {"status": "not_found"}

def run_discord_self_test_flow(channel=None, initial_msg=None, loop=None):
    acquired = False
    for _ in range(6):
        if acquire_operation("Weekly Self-Test (Discord)"):
            acquired = True
            break
        time.sleep(300)
        
    if not acquired:
        if initial_msg and loop:
            busy_embed = discord.Embed(
                title="⚠️ Self-Test Aborted",
                description="The bot was busy with another operation for over 30 minutes.",
                color=0xe67e22
            )
            asyncio.run_coroutine_threadsafe(initial_msg.edit(embed=busy_embed), loop)
        return

    status_msg = initial_msg
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
        
        start_embed = discord.Embed(
            title="🧪 Weekly Self-Test Started",
            description=(
                f"🌲 **Park:** {park}\n"
                f"📅 **Date:** Wednesday (`{target_date_str}`)\n\n"
                f"⌛ *Attempting automated booking...*"
            ),
            color=0x9b59b6
        )
        if status_msg and loop:
            asyncio.run_coroutine_threadsafe(status_msg.edit(embed=start_embed), loop)
        elif channel and loop:
            future = asyncio.run_coroutine_threadsafe(channel.send(embed=start_embed), loop)
            status_msg = future.result(timeout=10)
            
        book_transaction_time = datetime.datetime.now(datetime.timezone.utc)
        
        # Step 1: Book the park with real-time live step updates
        args = [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "reserve.py"), "book", "--park", park, "--date", target_date_str, "--headless", "true", "--skip-email-check"]
        proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        conf_num = None
        for line in iter(proc.stdout.readline, ""):
            line_str = line.strip()
            if "[PROGRESS]" in line_str:
                try:
                    parts = line_str.split("[PROGRESS]")[1].strip().split("|")
                    cur_step = "Processing"
                    cur_desc = "Executing step..."
                    cur_img = None
                    for p in parts:
                        p = p.strip()
                        if p.startswith("Step:"):
                            cur_step = p.replace("Step:", "").strip()
                        elif p.startswith("Desc:"):
                            cur_desc = p.replace("Desc:", "").strip()
                        elif p.startswith("Image:"):
                            cur_img = p.replace("Image:", "").strip()
                            
                    step_embed = discord.Embed(
                        title=f"🧪 Self-Test: Booking {park} ({cur_step})",
                        description=f"📅 **Date:** Wednesday (`{target_date_str}`)\n📝 **Status:** {cur_desc}",
                        color=0x3498db
                    )
                    file_to_send = None
                    if cur_img and os.path.exists(cur_img):
                        file_to_send = discord.File(cur_img, filename="progress.png")
                        step_embed.set_image(url="attachment://progress.png")
                        
                    if status_msg and loop:
                        asyncio.run_coroutine_threadsafe(
                            status_msg.edit(embed=step_embed, attachments=[file_to_send] if file_to_send else []),
                            loop
                        )
                except Exception:
                    pass
            if "CONFIRMATION_NUMBER=" in line_str:
                conf_num = line_str.split("CONFIRMATION_NUMBER=")[1].strip()
                
        proc.stdout.close()
        proc.stderr.close()
        proc.wait()
        
        booking_success = (proc.returncode == 0) and (conf_num is not None)
        if not booking_success:
            err_embed = discord.Embed(
                title="❌ Self-Test Failed at Booking Step",
                description=f"Automated booking for **{park}** on `{target_date_str}` failed.\nUse `❓ Check Errors` for details.",
                color=0xe74c3c
            )
            if status_msg and loop:
                asyncio.run_coroutine_threadsafe(status_msg.edit(embed=err_embed, attachments=[]), loop)
            return

        step2_embed = discord.Embed(
            title="✅ Self-Test: Booking Successful!",
            description=(
                f"🌲 **Park:** {park}\n"
                f"🔑 **Confirmation #:** `{conf_num}`\n\n"
                f"📥 *Verifying booking confirmation email via IMAP...*"
            ),
            color=0x3498db
        )
        if status_msg and loop:
            asyncio.run_coroutine_threadsafe(status_msg.edit(embed=step2_embed), loop)

        # Step 2: Verify booking email
        book_email_res = poll_email_verification_for_discord_selftest("book", book_transaction_time, max_attempts=6, delay=20)
        book_email_ok = book_email_res.get("status") == "found"
        
        time.sleep(5)
        cancel_transaction_time = datetime.datetime.now(datetime.timezone.utc)
        
        # Step 3: Cancel the booking
        cancel_args = [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "reserve.py"), "cancel", "--reservation", conf_num, "--headless", "true", "--skip-email-check"]
        c_res = subprocess.run(cancel_args, capture_output=True, text=True, timeout=90)
        cancel_success = (c_res.returncode == 0)
        
        cancel_email_ok = False
        cancel_email_res = {}
        if cancel_success:
            cancel_email_res = poll_email_verification_for_discord_selftest("cancel", cancel_transaction_time, max_attempts=6, delay=20)
            cancel_email_ok = cancel_email_res.get("status") == "found"

        # Step 4: Summary Card
        if booking_success and book_email_ok and cancel_success and cancel_email_ok:
            overall = "✅ **PASS (100% Verified)**"
            summary_embed = discord.Embed(
                title=f"🎉 Weekly Self-Test Summary: {overall}",
                description=(
                    f"📍 **Park:** {park}\n"
                    f"📅 **Date:** Wednesday (`{target_date_str}`)\n"
                    f"🔑 **Confirmation #:** `{conf_num}`\n\n"
                    f"📋 **Detailed Verification Steps:**\n"
                    f"• 🌐 Playwright Booking: ✅ Pass\n"
                    f"• 📧 Booking Email IMAP: ✅ Verified ({book_email_res.get('time')})\n"
                    f"• 🌐 Playwright Cancellation: ✅ Pass\n"
                    f"• 📧 Cancellation Email IMAP: ✅ Verified ({cancel_email_res.get('time')})"
                ),
                color=0x2ecc71
            )
        else:
            overall = "⚠️ **PARTIAL / ISSUES DETECTED**"
            b_str = f"✅ Verified ({book_email_res.get('time')})" if book_email_ok else "⚠️ Not Found"
            c_str = "✅ Pass" if cancel_success else "❌ Failed"
            ce_str = f"✅ Verified ({cancel_email_res.get('time')})" if cancel_email_ok else "⚠️ Not Found"
            summary_embed = discord.Embed(
                title=f"⚠️ Weekly Self-Test Summary: {overall}",
                description=(
                    f"📍 **Park:** {park}\n"
                    f"📅 **Date:** Wednesday (`{target_date_str}`)\n"
                    f"🔑 **Confirmation #:** `{conf_num}`\n\n"
                    f"📋 **Detailed Verification Steps:**\n"
                    f"• 🌐 Playwright Booking: ✅ Pass\n"
                    f"• 📧 Booking Email IMAP: {b_str}\n"
                    f"• 🌐 Playwright Cancellation: {c_str}\n"
                    f"• 📧 Cancellation Email IMAP: {ce_str}"
                ),
                color=0xe67e22
            )
        if status_msg and loop:
            asyncio.run_coroutine_threadsafe(status_msg.edit(embed=summary_embed), loop)
    except Exception as ex:
        if status_msg and loop:
            err_embed = discord.Embed(
                title="❌ Self-Test Exception",
                description=str(ex),
                color=0xe74c3c
            )
            asyncio.run_coroutine_threadsafe(status_msg.edit(embed=err_embed), loop)
    finally:
        release_operation()

def get_discord_selftest_schedule(config):
    import hashlib
    user_seed = str(config.get("discord_channel_id") or config.get("discord_allowed_user_ids") or "discord_default")
    hash_int = int(hashlib.md5(user_seed.encode("utf-8")).hexdigest(), 16)
    total_offset_secs = hash_int % (180 * 60)
    offset_hours = total_offset_secs // 3600
    offset_minutes = (total_offset_secs % 3600) // 60
    target_hour = 6 + offset_hours
    target_minute = offset_minutes
    return target_hour, target_minute

def discord_selftest_loop(main_loop):
    time.sleep(60) # Wait 60 seconds after boot
    target_hour, target_minute = get_discord_selftest_schedule(load_config())
    print(f"Scheduled weekly Discord self-test for Thursdays at {target_hour:02d}:{target_minute:02d} (staggered per-user offset).")
    
    while True:
        try:
            now = datetime.datetime.now()
            target_hour, target_minute = get_discord_selftest_schedule(load_config())
            
            # Check if it is Thursday (weekday = 3) and current time matches or passed target_time
            if now.weekday() == 3 and (now.hour > target_hour or (now.hour == target_hour and now.minute >= target_minute)):
                last_date = ""
                json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "last_selftest_discord.json")
                if os.path.exists(json_path):
                    with open(json_path, "r", encoding="utf-8") as f:
                        try:
                            data = json.load(f)
                            last_date = data.get("last_run_date", "")
                        except Exception:
                            pass
                            
                today_str = now.strftime("%Y-%m-%d")
                if last_date != today_str:
                    print(f"Triggering scheduled Thursday self-test for Discord at {now.strftime('%Y-%m-%d %H:%M:%S')}...")
                    channel = None
                    if CHANNEL_ID:
                        try:
                            channel = bot.get_channel(int(CHANNEL_ID))
                        except Exception:
                            pass
                    run_discord_self_test_flow(channel=channel, loop=main_loop)
                    try:
                        with open(json_path, "w", encoding="utf-8") as f:
                            json.dump({"last_run_date": today_str, "status": "completed"}, f, indent=4)
                    except Exception:
                        pass
        except Exception as e:
            print(f"Error in discord_selftest_loop: {e}")
        time.sleep(300)

async def handle_selftest_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🧪 Weekly Self-Test Started",
        description="⏳ Initializing automated booking and cancellation verification flow...",
        color=0x9b59b6
    )
    if not interaction.response.is_done():
        await interaction.response.send_message(embed=embed, ephemeral=False)
        msg = await interaction.original_response()
    else:
        msg = await interaction.followup.send(embed=embed, ephemeral=False)

    loop = asyncio.get_running_loop()
    threading.Thread(
        target=run_discord_self_test_flow,
        kwargs={"channel": interaction.channel, "initial_msg": msg, "loop": loop},
        daemon=True
    ).start()

# -------------------------------------------------------------
# Slash Commands Registration
# -------------------------------------------------------------

@bot.tree.command(name="menu", description="Display the Ontario Parks Pull-Out Control Dashboard")
async def cmd_menu(interaction: discord.Interaction):
    if not is_authorized(interaction.user.id):
        await interaction.response.send_message("⛔ Unauthorized.", ephemeral=True)
        return
    embed = create_dashboard_embed()
    await interaction.response.send_message(embed=embed, view=ControlDashboardView())

@bot.tree.command(name="list", description="List all active Ontario Parks reservations")
async def cmd_list(interaction: discord.Interaction):
    if not is_authorized(interaction.user.id):
        await interaction.response.send_message("⛔ Unauthorized.", ephemeral=True)
        return
    await handle_list_command(interaction)

@bot.tree.command(name="book", description="Open the park booking wizard")
async def cmd_book(interaction: discord.Interaction):
    if not is_authorized(interaction.user.id):
        await interaction.response.send_message("⛔ Unauthorized.", ephemeral=True)
        return
    view = ParkButtonsView()
    embed = discord.Embed(
        title="🌲 Ontario Parks Booking Wizard",
        description="Select a provincial park below to begin:",
        color=0x2b82d9
    )
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

@bot.tree.command(name="cancel", description="View active bookings with one-click cancel buttons")
async def cmd_cancel(interaction: discord.Interaction):
    if not is_authorized(interaction.user.id):
        await interaction.response.send_message("⛔ Unauthorized.", ephemeral=True)
        return
    await handle_cancel_list_command(interaction)

@bot.tree.command(name="selftest", description="Run the automated weekly self-test verification")
async def cmd_selftest(interaction: discord.Interaction):
    if not is_authorized(interaction.user.id):
        await interaction.response.send_message("⛔ Unauthorized.", ephemeral=True)
        return
    await handle_selftest_command(interaction)

@bot.tree.command(name="errors", description="View details of the last failed execution")
async def cmd_errors(interaction: discord.Interaction):
    if not is_authorized(interaction.user.id):
        await interaction.response.send_message("⛔ Unauthorized.", ephemeral=True)
        return
    embed = discord.Embed(
        title="📋 Last Execution Error / Log",
        description=f"```\n{LAST_ERROR[:1900]}\n```",
        color=0xe74c3c if "error" in LAST_ERROR.lower() else 0x95a5a6
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

# -------------------------------------------------------------
# Bot Lifecycle Events
# -------------------------------------------------------------

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    if not is_authorized(message.author.id):
        return
        
    text = message.content.strip().lower()
    if text in ["/menu", "!menu", "menu", "help", "!help", "/help", "/start", "start"]:
        embed = create_dashboard_embed()
        await message.channel.send(embed=embed, view=ControlDashboardView())
    elif text in ["/list", "!list", "list"]:
        bookings = get_active_reservations()
        if not bookings:
            embed = discord.Embed(title="📋 Active Bookings", description="No active bookings found.", color=0x95a5a6)
            await message.channel.send(embed=embed)
        else:
            desc_lines = []
            for idx, b in enumerate(bookings, 1):
                desc_lines.append(f"**{idx}. {b.get('park_name')}**\n📅 Date: `{b.get('date_str')}`\n🔑 Conf #: `{b.get('conf_number')}`\n")
            embed = discord.Embed(title="📋 Active Bookings", description="\n".join(desc_lines), color=0x2ecc71)
            await message.channel.send(embed=embed, view=CancelConfirmationView(bookings))
    elif text in ["/book", "!book", "book"]:
        view = ParkButtonsView()
        embed = discord.Embed(title="🌲 Ontario Parks Booking Wizard", description="Select a park to begin:", color=0x2b82d9)
        await message.channel.send(embed=embed, view=view)

@bot.event
async def on_ready():
    bot.add_view(ControlDashboardView())
    print(f"Logged in as Discord Bot: {bot.user.name} (ID: {bot.user.id})")
    try:
        for g in bot.guilds:
            bot.tree.copy_global_to(guild=g)
            await bot.tree.sync(guild=g)
            print(f"Synced slash commands instantly to guild '{g.name}' (ID: {g.id})")
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} Discord slash commands globally.")
    except Exception as e:
        print(f"Failed to sync slash commands: {e}")

    # Post Dashboard to designated channel if configured
    if CHANNEL_ID:
        try:
            channel = bot.get_channel(int(CHANNEL_ID))
            if not channel:
                channel = await bot.fetch_channel(int(CHANNEL_ID))
                
            if channel:
                # Check if dashboard already exists in the last 10 messages
                found = False
                async for m in channel.history(limit=10):
                    if m.author.id == bot.user.id and m.embeds and "Ontario Parks Reservation Assistant" in (m.embeds[0].title or ""):
                        found = True
                        break
                if not found:
                    embed = create_dashboard_embed()
                    await channel.send(embed=embed, view=ControlDashboardView())
                    print(f"Posted Control Dashboard to channel #{getattr(channel, 'name', CHANNEL_ID)} ({CHANNEL_ID})")
                else:
                    print(f"Control Dashboard already present in channel #{getattr(channel, 'name', CHANNEL_ID)}.")
        except Exception as ex:
            print(f"Could not auto-post dashboard to channel {CHANNEL_ID}: {ex}")

    # Launch Thursday scheduled self-test loop in background thread
    threading.Thread(target=discord_selftest_loop, args=(asyncio.get_running_loop(),), daemon=True).start()

def main():
    if not TOKEN:
        print("ERROR: DISCORD_TOKEN is not configured in .env or ontario_parks_config.json!")
        sys.exit(1)
        
    print("Starting Discord Bot...")
    bot.run(TOKEN)

if __name__ == "__main__":
    main()
