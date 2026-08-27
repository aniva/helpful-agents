# Implementation Plan: Interactive Highlight Splicing for Video 002

We will process `VID_20251121_102819_00_002.mp4` to extract and stitch only the riding and launching segments (with smooth transitions) at the same 4K resolution and frame rate.

To ensure 100% precision without tedious manual video editing, we have pre-built an **interactive highlight selection application** and a dedicated **FFmpeg crossfade stitching script**.

---

## Proposed Solution

1. **Pre-extracted Frames**: We have already extracted a frame every 5 seconds from the 30-minute 4K video, resized them to a lightweight 480x270 format, and saved them to the scratch directory.
2. **Dynamic Heuristics**: We analyzed the extracted frames using HSV color space heuristics to automatically classify each frame:
   - **Shore (Launching)**: Detected based on sand/beach color distributions.
   - **Riding**: Detected based on high-value, low-saturation white pixels representing water wake and spray.
   - **Discard (Fallen/Swimming)**: Default state when no wake or sand is present.
3. **Interactive Splicer UI**: We compiled this metadata into a sleek, dark-mode local HTML interface that lets you inspect every 5-second block, verify the suggestions, and tweak the ranges using keyboard and mouse shortcuts.
4. **Hardware-Accelerated Stitching**: We created `stitch_highlights.py` which takes the JSON config copied from the web app, generates a single-pass FFmpeg command using `xfade` (video crossfade) and `acrossfade` (audio crossfade), and renders the final 4K video using the NVIDIA GPU (`hevc_nvenc`).

---

## Proposed Changes

### [Core Splicing Pipeline]

#### [NEW] [stitch_highlights.py](file:///wsl.localhost/Ubuntu/home/me/repos/helpful-agents/insta_highlights_creator_v2/stitch_highlights.py)
*   Python script that reads the selection configuration and executes the multi-input FFmpeg pipeline with 1-second crossfades for both video and audio. Uses `hevc_nvenc` hardware encoding.

#### [NEW] [index.html](file:///wsl.localhost/Ubuntu/home/me/repos/helpful-agents/insta_highlights_creator_v2/processScratch/index.html)
*   Sleek local HTML page displaying the grid of 360 thumbnails, suggestions, and timeline stats. Includes "Copy Config" action to easily transfer selection data back.

---

## Verification & Execution Steps

### Step 1: Open the Splicer App
Open this file in your Windows browser or File Explorer:
`\\wsl.localhost\Ubuntu\home\me\repos\helpful-agents\insta_highlights_creator_v2\processScratch\index.html`

*   **Keyboard Shortcuts**:
    *   **Click** a frame to cycle: `Discard` (Gray) &rarr; `Riding` (Green) &rarr; `Shore` (Orange).
    *   **Shift + Click** to select a range! Click a card, hold Shift, and click another card to set the state of all cards in between.
    *   Click **"Copy Config to Clipboard"** when done.

### Step 2: Paste Config & Stitch
Paste the copied JSON config in the chat. We will run the stitching pipeline immediately to render your final video at:
`E:\202511_Insta360\yt_ready\002\VID_20251121_102819_00_002_highlights.mp4`

---

## Verification Plan

### Automated Tests
*   Once the config is received, we will run `stitch_highlights.py` in WSL:
    ```bash
    wsl python3 stitch_highlights.py \
      --video "E:\202511_Insta360\yt_ready\002\VID_20251121_102819_00_002.mp4" \
      --config '[YOUR_JSON_HERE]' \
      --output "E:\202511_Insta360\yt_ready\002\VID_20251121_102819_00_002_highlights.mp4"
    ```

### Manual Verification
*   Verify the final 4K video plays with smooth 1-second crossfades between the chosen launching/riding segments, maintaining 3840x2160 resolution and 29.97 fps.
