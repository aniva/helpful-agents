# GoPro Video Editing Workflow & Automation Pipeline

This document details the complete 4-step workflow we established to edit, process, render, and upload high-quality GoPro highlights.

---

## 📋 The 4-Step Workflow

### Step 1: Slice Video "As Is" in Shotcut (Visual Cuts Only)
1. Open Shotcut and import your raw, high-resolution GoPro clips.
2. Drag them onto the video track **V1** and perform your visual cuts (deleting parts you don't want, splicing, and stitching). 
3. *Do not perform any resizing, cropping, music mixing, or text overlays in Shotcut.* Just focus on raw visual cuts on a single timeline.

### Step 2: Save the Project MLT File
1. Save your Shotcut project file in your GoPro directory.
2. Filename convention for the automation scripts: **`draft.mlt`** (or `draft2.mlt` for your next project) in:
   `E:\20260627_GoPro\draft.mlt`

### Step 3: Run the Post-Processing Automation Scripts
The scripts automatically handle aspect ratio conforming, crop-scaling, music synthesis/mixing, text overlays, and GPU-accelerated rendering.

#### 3a. Generate Copyright-Free Audio (If needed)
If you need original, copyright-safe background music to prevent video blocks on YouTube/Instagram, run the music synthesis scripts:
* **Lullaby Waltz**: `python synth_music.py` (generates a nostalgic waltz-time chime lullaby).
* **Sporty Heartbeat**: `python synth_sport_beat.py` (generates a 120 BPM percussive sporty rhythm).

#### 3b. Run the Conformer & Renderer (`post_process.py`)
Run the post-processing script, specifying your desired settings:

```powershell
& 'C:\Users\me\AppData\Local\Temp\gopro_venv\Scripts\python.exe' `
  C:\Users\me\.gemini\antigravity\scratch\post_process.py `
  --draft "E:/20260627_GoPro/draft.mlt" `
  --aspect "1:1" `
  --title "My Video Highlight\n2026" `
  --end "Thanks for watching!" `
  --gpu
```

#### User Input & Options Supported:
* **Aspect Ratio (`--aspect`)**: Choose between standard square feed posts (`1:1`) or vertical portrait posts (`4:5`).
* **Resolution**: Automatically conformed to true 4K width (`2160x2160` for 1:1, or `2160x2700` for 4:5) to match high-resolution sources.
* **Frame Rate (FPS)**: Decodes and locks video timing and audio mixing to the native GoPro timebase (59.94 fps).
* **GPU Encoding (`--gpu`)**: Offloads H.264 video compression to your Nvidia card (`h264_nvenc`) with constant-quality controls (`cq=21`), dropping CPU usage and accelerating 4K render speeds by up to 20x.
* **Auto-Crops to Fill**: Automatically centers and crops source clips to fill the output canvas (no black bars).
* **Audio Track Mixing**: Mutes original camera audio and loops your selected background track, adjusting music volume level to a conformed 40%.
* **Centered Titles**: Overlays multi-line text aligned vertically and horizontally in the middle of the frame.

### Step 4: Transfer and Upload to Social Media
1. When rendering finishes, the script starts a local web server and generates a **QR Code image**.
2. Connect your phone to the **same Wi-Fi network** as your computer.
3. Scan the QR code or open the link on your phone:
   👉 **`http://192.168.1.11:8080/video.mp4`**
4. Save the 4K video to your camera roll and upload it directly to Instagram or YouTube!
5. Close the PowerShell console or tell the assistant to stop the server when done.
