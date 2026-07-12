---
name: ontario-parks-booking
description: >-
  Automates daily vehicle permit (DVP) reservations, lists active bookings,
  and cancels upcoming reservations on reservations.ontarioparks.ca headlessly.
---

# Ontario Parks Reservation Manager

## Overview
This skill automates booking daily vehicle permits (DVP) at Ontario Provincial Parks based on local wind and weather forecasts (useful for kiteboarding/windsurfing), lists active bookings, and cancels upcoming reservations headlessly using Playwright.

## Dependencies
None.

## Quick Start
To use this skill, run the core python script [reserve.py](file:///wsl.localhost/Ubuntu/home/me/repos/helpful-agents/ontario-parks/reserve.py) using `uv run python reserve.py` or `.venv/Scripts/python.exe reserve.py` with the appropriate subcommand:

1. **Book a permit:**
   ```bash
   uv run python reserve.py book --park "Sibbald Point" --date "tomorrow"
   ```
2. **List active bookings:**
   ```bash
   uv run python reserve.py list
   ```
3. **Cancel a booking:**
   ```bash
   uv run python reserve.py cancel --reservation "INOP26-7139739B1"
   ```

## Configuration
All settings and credentials are saved locally in [ontario_parks_config.json](file:///wsl.localhost/Ubuntu/home/me/repos/helpful-agents/ontario-parks/ontario_parks_config.json). Ensure the following fields are populated:
* `email`: Account email address.
* `ontario_parks_password`: Account password (required for headless automated login).
* `permit_number`: Seasonal permit number.
* `vehicle_plate`: Vehicle license plate.
* `vehicle_province`: Vehicle province (e.g., `ONTARIO`).
* `telegram_token` & `telegram_chat_id`: Tokens for notifications.

## Utility Scripts
The helper script `reserve.py` manages all actions:
* **`book`**: Automates the search, selection, and the entire 5-step checkout wizard + vehicle pre-registration.
* **`list`**: Scrapes current bookings and stores them in `active_reservations.json` for agent/bot query.
* **`cancel`**: Clicks through the cancellation sequence for the matching reservation.

## Common Mistakes
* **Missing Password**: Forgetting to add `"ontario_parks_password"` to `ontario_parks_config.json` will cause headless login to fail.
* **Incorrect Date format**: Specify `--date` as `today`, `tomorrow`, `day_after`, or `YYYY-MM-DD`.
* **Git leaking credentials**: Ensure `ontario_parks_config.json` is always listed in `.gitignore`.
