# Ontario Park Daily Vehicle Permit Automation

A headed Playwright automation tool to search, rank, and book daily vehicle permits (DVP) at Ontario Provincial Parks based on local wind and weather forecasts (tailored for kiteboarding/windsurfing).

## Features

- **Wind Forecast Ranking**: Fetches forecast data from Open-Meteo API for participating parks and sorts them by maximum wind speed on your selected date.
- **WAF Bypass (Headed Browser)**: Runs Playwright in headed mode (`headless=False`) using your local environment to bypass Azure Front Door WAF blocks.
- **Autofill details**: Fills out your vehicle plate, province, seasonal permit number, and contact phone automatically on the booking details page.
- **Gmail IMAP Check**: Checks your inbox for the confirmation email from Ontario Parks.
- **Telegram Notification**: Sends a summary of the booking (including confirmation number, park, vehicle, and forecast) directly to your Telegram bot.

---

## Setup Instructions

### 1. Prerequisite Packages
Make sure you have [uv](https://github.com/astral-sh/uv) installed on your system. 

Run the following command to download and install Playwright's browser engines:
```bash
uv run playwright install chromium
```

### 2. Configuration Settings
All user settings are saved locally in `ontario_parks_config.json` (which is excluded from Git tracking for privacy). The file must contain:
- **Email**: Your email address
- **Plate**: Your vehicle license plate
- **Permit Number**: Your seasonal park permit serial number
- **Telegram Token**: Your Telegram Bot API token

### 3. Retrieve Telegram Chat ID
To send you messages, the bot needs to know your chat ID. The script contains a helper to resolve it automatically:
1. Open your Telegram app.
2. Find the bot using your token or lookup username.
3. Send a message to your bot (e.g. `/start` or `hi`).
4. Run the helper command:
   ```bash
   uv run python reserve.py --setup-telegram
   ```
5. The helper will poll your bot, capture your Chat ID, update `ontario_parks_config.json`, and send a success confirmation message.

---

## How to Run

Simply run:
```bash
uv run python reserve.py
```

### Execution Flow:
1. **Choose Reservation Date**: Select between **Today**, **Tomorrow**, or **Day after tomorrow**.
2. **Review Wind & Weather Rankings**: The script displays kiting parks ranked by maximum daylight wind speed. Select the number of the park you wish to reserve.
3. **Automated Search Navigation**: Playwright opens and performs the search, clicks on the date cell in the grid, and navigates to the booking details page.
4. **Log In (Manual Check)**: If not logged in, the browser will wait. Log in in the browser window, then press `Enter` in the console.
5. **Autofill & Submit**: The script automatically checks "Seasonal Vehicle Permit Holder", fills in your pass number `S-2632347`, vehicle plate `ATXJ307`, province `ONTARIO`, and clicks confirm.
6. **Checkout**: Review the final booking details ($0.00 charge), click checkout/confirm in the browser, and press `Enter` in the console once completed.
7. **Confirmation & Notifications**: The script extracts your confirmation number, takes a screenshot of the confirmation page, verifies the email receipt in Gmail, and sends a notification to Telegram!
