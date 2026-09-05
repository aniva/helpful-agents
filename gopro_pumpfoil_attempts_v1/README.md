# 🏄 GoPro Pump Foil Attempts Extractor (v1.8)

A high-performance, hardware-accelerated local web application to browse, mark, trim, and stitch pump foil attempts directly from raw GoPro camera footage.

Zero cloud dependencies. Zero external subscriptions. Runs 100% locally on your machine with direct NVIDIA GPU acceleration or multi-core CPU encoding.

---

## ⚡ Key Highlights

- **Auto-Detects GoPro SD Card:** Automatically discovers `DCIM/100GOPRO` across connected drives (e.g. `F:\DCIM\100GOPRO`).
- **Continuous Vertical Timeline:** All GoPro chapters and recording sessions are ordered chronologically. Browse seamlessly using vertical mouse wheel scrolling.
- **90x Accelerated Proxy Scanning:** Extracts thumbnail timelines in seconds utilizing GoPro `.LRV` proxy files.
- **Hardware Benchmarking & NVENC Acceleration:** Calibrates encoding performance (e.g. NVIDIA RTX GPU `hevc_nvenc` running at 45+ fps) to deliver accurate live progress and ETA.
- **Instant Multi-Cut Selection:** 
  - Click any frame to set **Attempt Start** &rarr; click a later frame to finish the attempt.
  - To cancel or unmark an in-progress start frame, click the frame again or tap its `×` cancel badge.
- **SD Card State & Crash Resilience:** Every selection is auto-saved to `<destination>/cuts.txt` and mirrored onto the SD card (`.pumpfoil_session.json` and `cuts.txt`). Restarting or reopening restores your exact state.
- **Orderly Cancellation & Redo:** Cancel any cut or stitch operation at any point cleanly without corrupting files or losing your marked attempts.
- **Dip-Fade Transitions:** Cut individual pristine 4K 60fps MP4 clips or stitch them into a continuous highlight reel with seamless 0.35-second dip-fades.

---

## 🛠️ System Requirements

- **Operating System:** Windows 10/11, macOS, or Linux (including WSL2 Ubuntu).
- **Python:** Python 3.8 or newer (uses standard library only — no `pip install` required!).
- **FFmpeg:** FFmpeg and FFprobe installed and available in your system `PATH`.
  - *Optional (Recommended):* NVIDIA GPU with CUDA/NVENC support for ultra-fast 4K 60fps hardware encoding.

---

## 📦 Installation & Setup

### 1. Clone the Repository
```bash
git clone https://github.com/aniva/helpful-agents.git
cd helpful-agents/gopro_pumpfoil_attempts_v1
```

### 2. Verify FFmpeg
Ensure `ffmpeg` is accessible in your terminal or command prompt:
```bash
ffmpeg -version
```
> **Windows Tip:** If you don't have FFmpeg installed, you can install it via winget:
> ```cmd
> winget install Gyan.FFmpeg
> ```

---

## 🚀 Running the App

### Windows
Double-click `launch_app.cmd` or run:
```cmd
launch_app.cmd
```
*(Alternatively: `py server\app.py`)*

### Linux / macOS / WSL
```bash
chmod +x launch_app.sh
./launch_app.sh
```
*(Alternatively: `python3 server/app.py`)*

The server starts locally at `http://localhost:8765` and automatically opens in your default web browser.

---

## 📖 Step-by-Step Usage Guide

### 1. Detect SD Card & Set Destination
- Insert your GoPro SD card into your computer.
- The app automatically detects the GoPro source folder (e.g., `F:\DCIM\100GOPRO`).
- The app recommends an output destination formatted by recording date and start time:
  `E:\GOPRO_<YYYYMMDD>_<HHMM>`

### 2. Choose Sampling Interval & Load Timeline
- Select your preferred thumbnail interval:
  - **1.0 sec:** Ultra-fine frame accuracy.
  - **2.0 sec:** Detailed inspection.
  - **4.0 sec (Default):** Optimal balance of speed and frame density.
  - **6.0 sec:** Fast overview for long multi-hour sessions.
- Click **⚡ Load Timeline**.
- *Pre-scan prompt:* If cached thumbnails exist from an earlier run, click **Reuse Existing** for instantaneous sub-second loading.

### 3. Mark Pump Foil Attempts
- Scroll vertically through the timeline using your mouse wheel.
- **Mark Start:** Click on the frame where your foil attempt begins (dock start, paddle launch, or flatwater pump start).
- **Mark Stop:** Click on the frame where you touch down or wipe out.
- The attempt is created immediately (e.g., `Attempt_1 (16s)`).
- **Unmark / Cancel Start:** If you clicked a start frame by mistake, click it again or click its floating `×` badge.
- **Delete an Attempt:** Click the red `×` button on any stop frame or in the **Cuts List** sidebar.
- **Rename:** Click the label in the sidebar to give the attempt a custom name (e.g. `Dock_Start_Deep_Pump`).

### 4. Render Attempts & Highlight Reel
- **✂️ Cut Attempts:** Extracts individual 4K 60fps clips into `<destination>/attempts/`.
- **🎬 Cut & Stitch Highlights:** Renders each attempt and automatically combines them into `PumpFoil_Highlights.mp4` with smooth dip-fade transitions.
- **Live Progress & ETA:** Displays live encoding speed (FPS), real-time percentages, and estimated time remaining.
- **Cancellation:** Hit **🛑 Cancel Processing** at any time to abort safely. All your marked cuts remain on the timeline for you to adjust and re-render.

---

## 📁 Output Directory Structure

```text
E:\GOPRO_20260627_1009/
├── cuts.txt                        # Plain-text cut list (timestamped and labeled)
├── session_state.json              # App session state for instant restore
├── PumpFoil_Highlights.mp4         # Stitched highlight reel with dip-fades
├── attempts/                       # Individual rendered attempt clips
│   ├── Attempt_1_GX015264_00-52-01-08.mp4
│   └── Attempt_2_GX015264_02-44-02-48.mp4
└── .thumbnails_4s/                 # Cached thumbnail previews (reused across runs)
```

---

## ⚖️ License
MIT License. Built for pump foilers and action sports creators.