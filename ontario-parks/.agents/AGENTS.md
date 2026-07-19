# Ontario Parks Automation - Agent Guidelines & Architecture Reference

This document provides developer guidelines, architectural context, and implementation details for agentic AI assistants working on this repository.

---

## 🏗️ System Architecture

The project consists of two primary components:
1. **`bot.py` (Telegram Daemon / Coordinator)**: A persistent, long-running polling service that listens for Telegram messages and inline query button clicks.
2. **`reserve.py` (Subprocess Executor)**: A short-lived CLI command that automates the headed/headless Playwright browser interaction, parses weather forecasts, and performs IMAP email polling.

### Subprocess Execution & Progress Tracking:
* To avoid blocking the Telegram listener thread, all heavy tasks (booking, cancelling, listing) are spawned as subprocesses (`reserve.py`) in background threads using `run_subprocess_with_progress`.
* The subprocess communicates its progress back to the daemon by printing specialized `[PROGRESS]` prefix tags to `stdout`. The daemon parses these tags in real-time to update the user with progress steps and debug screenshots:
  ```
  [PROGRESS] Step: <Step Name> | Desc: <Description> | Image: <ScreenshotFilename>
  ```
* A watchdog timer is configured to automatically kill stuck subprocesses after a timeout (default: 360 seconds for booking, 90 seconds for cancelling).

---

## 🚗 Booking & Checkout Flow (`reserve.py`)

The automated checkout is a multi-step wizard matching the Ontario Parks daily vehicle permit workflow:
1. **Search Grid / Map View**: Performs search for park and date.
2. **Wasaga Beach Exception**: If a map-view is loaded (e.g. Wasaga Beach has sub-locations), the script toggles list-view `#list-view-button-button`, clicks the matching sub-location card, and enters the grid.
3. **Availability Grid**: Clicks the target date cell if available.
4. **Log In Check**: Fills credentials and logs in if a login form is displayed.
5. **Autofill (Step 6)**: Fills vehicle plate, province, selects "Seasonal Vehicle Permit Holder", and enters the pass number.
6. **Final Confirmation (Step 7)**: Clicks "Confirm booking" and waits for success/results page redirection.

### Success Page Automation (Preregister vs Check-In):
* If the reservation date is in the **future**, a `"Preregister"` button is shown.
* If the reservation date is **tomorrow or today**, a `"Check in"` button is shown.
* The script handles both button flows on the success page: clicking the entry button and then clicking `"Preregister now"`, `"Confirm check in"`, or `"Check in now"` to finish the registration.

---

## ✉️ IMAP Email Verification

* Verification check uses IMAP to poll the user's Gmail inbox for confirmation and cancellation emails from `confirmations@camis.com`.
* **Exclusions**: Same-day or next-day bookings trigger automated check-in reminder emails from the site. The email polling logic explicitly filters out and ignores these check-in emails (by skipping messages with subjects containing `"check in"` or `"check-in"`), preventing them from being falsely matched as the booking confirmation.
* **Correlations**: The transaction email checker accepts a `transaction_time` anchor in UTC and filters out any historical emails. It matches body content to confirm whether the email type (booking vs cancellation) correlates to the active transaction.

---

## 🚫 Duplicate Date Booking Validation

* Before launching a booking thread, `bot.py` queries `active_reservations.json` (the local cache).
* **Same Park, Same Day**: Blocks the transaction immediately and notifies the user of the duplicate.
* **Different Park, Same Day**: Warns the user of the overlap but proceeds with launching the booking subprocess.

---

## 🔧 Deployment & Maintenance

* The bot daemon runs as a systemd user service (`ontario_parks_bot.service`) configured under `~/.config/systemd/user/`.
* When updating or adding features, ensure to verify syntax with:
  ```bash
  python3 -m py_compile bot.py reserve.py
  ```
* Always reload and restart the user service daemon on the server:
  ```bash
  systemctl --user daemon-reload
  systemctl --user restart ontario_parks_bot
  ```
