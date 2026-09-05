# GoPro Pump Foil Attempts Extractor v1

A specialized, high-performance web tool and video processing engine to extract, trim, and stitch pump foil attempts directly from GoPro raw footage.

---

## Key Features

1. **Auto-Detect SD Card:**
   - Automatically scans system drives for `DCIM/100GOPRO` (e.g. `F:\DCIM\100GOPRO`).
   - Allows instant manual re-selection or folder browsing.
2. **Custom Destination Path:**
   - Defaults to e.g. `E:\<Date>_PumpFoil` with automatic creation and persistence.
3. **Continuous Chronological Vertical Timeline:**
   - All GoPro chapters and sessions arranged in true chronological order.
   - Natural mouse wheel up/down scrolling across the entire session.
   - Sticky chapter banners indicate which clip and time you are currently browsing.
4. **Configurable Sampling Interval:**
   - Choose frame sampling rates: `1.0s` (ultra-fine), `2.0s`, `4.0s` (default), or `6.0s`.
   - Accelerated 90x by GoPro `.LRV` proxy files and cached automatically.
5. **Instant Multi-Cut Selection (Zero Button Clicks):**
   - Click Frame A (Start) &rarr; Click Frame B (Stop) &rarr; Attempt created immediately.
   - Next click immediately starts the next attempt.
   - Interactive ribbons and timeline `×` buttons to adjust or delete cuts on the fly.
6. **Real-Time Auto-Save (`cuts.txt` & Crash Recovery):**
   - Every cut addition, rename, or deletion automatically syncs to `<destination>/cuts.txt` and `<destination>/session_state.json`.
   - Accidental tab closes or browser refreshes restore the exact state instantly.
7. **Hardware-Accelerated 4K60 NVENC Pipeline:**
   - NVIDIA CUDA decode + NVENC HEVC encoding (`-hwaccel cuda -c:v hevc_nvenc -cq 19 -c:a copy`).
   - Starts on a clean IDR keyframe at `00:00:00.000` (zero macroblocking / pixelation).
8. **One-Click Cut & Stitch:**
   - **Cut Attempts**: Renders individual pristine 4K 60fps clips into `attempts/`.
   - **Cut & Stitch**: Trims attempts AND stitches them into a final highlight video with smooth 0.35s dip-fade transitions.

---

## Quick Start

### Windows
Double-click:
```cmd
launch_app.cmd
```
*(Or run `py server\app.py` in terminal)*

### WSL / Linux
```bash
./launch_app.sh
```

Opens automatically at `http://localhost:8765`.