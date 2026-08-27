import os
import sys
import threading
import json
import traceback
from fastapi import FastAPI, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from video_processor import find_video_pairs, HighlightAnalyzer, HighlightGenerator, prepare_input_videos

app = FastAPI(title="Insta360 X5 Kitefoil Highlights Creator")

# CORS middleware for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global job state
job_state = {
    "status": "idle",       # idle, scanning, rendering, mixing, done, error
    "progress": 0.0,
    "log": "",
    "error_message": "",
    "result_video": ""
}
job_lock = threading.Lock()

def update_job(status=None, progress=None, log_line=None, error=None, result=None):
    with job_lock:
        if status is not None:
            job_state["status"] = status
        if progress is not None:
            job_state["progress"] = float(progress)
        if log_line is not None:
            job_state["log"] += log_line + "\n"
        if error is not None:
            job_state["error_message"] = str(error)
        if result is not None:
            job_state["result_video"] = result

@app.get("/api/scan-drives")
def scan_drives(custom_path: str = None):
    """
    Scans media paths to locate paired Insta360 video files.
    """
    paths_to_scan = []
    
    if custom_path:
        paths_to_scan.append(custom_path)
    else:
        # Cross-platform drive scanning
        if sys.platform == "win32":
            # Scan letters D: to Z:
            import string
            for letter in string.ascii_uppercase[3:]:
                drive = f"{letter}:\\"
                if os.path.exists(drive):
                    paths_to_scan.append(drive)
                    # Common Insta360 DCIM subfolders
                    paths_to_scan.append(os.path.join(drive, "DCIM", "Camera01"))
        else: # Linux / macOS
            # Scan typical mount points
            user = os.environ.get("USER", "user")
            media_paths = [
                f"/media/{user}",
                f"/run/media/{user}",
                "/media",
                "/mnt"
            ]
            for mp in media_paths:
                if os.path.exists(mp):
                    paths_to_scan.append(mp)
                    # Check subfolders in mounts
                    try:
                        for entry in os.scandir(mp):
                            if entry.is_dir():
                                paths_to_scan.append(entry.path)
                                # DCIM subfolder
                                dcim = os.path.join(entry.path, "DCIM", "Camera01")
                                if os.path.exists(dcim):
                                    paths_to_scan.append(dcim)
                    except Exception:
                        pass
                        
        # Always allow scanning the local project scratch folder
        paths_to_scan.append(os.getcwd())

    all_pairs = []
    scanned_folders = []
    
    for path in paths_to_scan:
        if not path or not os.path.exists(path):
            continue
        try:
            pairs = find_video_pairs(path)
            if pairs:
                scanned_folders.append(path)
                for p in pairs:
                    all_pairs.append({
                        "folder": path,
                        "prefix": p["prefix"],
                        "front": p["front"],
                        "rear": p["rear"],
                        "front_name": os.path.basename(p["front"]),
                        "rear_name": os.path.basename(p["rear"])
                    })
        except Exception:
            pass

    return {
        "scanned_paths": list(set(paths_to_scan)),
        "detected_folders": scanned_folders,
        "video_pairs": all_pairs
    }

def bg_process_highlights(front_path, rear_path, music_path, duration, 
                           p_rider, p_kite, p_scenery, format_type, 
                           mix_music_ratio, mix_bg_ratio, is_preview):
    temp_video = "temp_render.mp4"
    final_video = "final_output.mp4"
    video_front, video_rear, is_temp = front_path, rear_path, False
    
    try:
        update_job(status="scanning", progress=0.0, log_line="Preparing input videos...")
        
        # Extract tracks if multi-stream
        output_dir = os.path.dirname(final_video) if os.path.dirname(final_video) else "."
        video_front, video_rear, is_temp = prepare_input_videos(front_path, rear_path, output_dir)
        
        update_job(status="scanning", progress=0.0, log_line="Starting YOLOv8 Object Detection...")
        
        # 1. Run YOLOv8 scan
        analyzer = HighlightAnalyzer(model_size="n")
        
        def scan_prog(p):
            update_job(progress=p * 0.4) # Scanning covers first 40% of overall progress
            
        timeline = analyzer.analyze_video(video_front, video_rear, progress_callback=scan_prog)
        
        update_job(log_line=f"Video scan complete. Found {len(timeline)} frames of metadata.")
        update_job(status="rendering", progress=0.4, log_line="Planning focus segments and starting perspective rendering...")
        
        # 2. Plan segments
        # Limit target duration if it's a draft preview
        render_duration = 30.0 if is_preview else float(duration)
        generator = HighlightGenerator(timeline, W_out=960 if is_preview else (1080 if format_type == "Instagram" else 1920), 
                                       H_out=540 if is_preview else (1920 if format_type == "Instagram" else 1080), 
                                       format_type=format_type)
        
        segments = generator.plan_highlights(render_duration, p_rider, p_kite, p_scenery)
        update_job(log_line=f"Planned {len(segments)} segments for output highlights.")
        
        # 3. Render reframed frames
        def render_prog(p):
            # Rendering covers progress from 40% to 90%
            update_job(progress=0.4 + p * 0.5)
            
        generator.render_video(video_front, video_rear, segments, temp_video, progress_callback=render_prog)
        update_job(log_line="Perspective rendering completed. Starting audio mixing...")
        
        # 4. Mix Audio using FFmpeg
        update_job(status="mixing", progress=0.9, log_line="Executing FFmpeg audio mixing...")
        
        # Check if music path exists
        if not music_path or not os.path.exists(music_path):
            # Create a silent track or copy without audio if no music provided (using original front_path for audio)
            update_job(log_line="No background music found, exporting with ambient sound only.")
            cmd_mix = ['ffmpeg', '-y', '-i', temp_video, '-i', front_path, '-map', '0:v', '-map', '1:a', '-c:v', 'copy', '-c:a', 'aac', '-shortest', final_video]
            import subprocess
            subprocess.run(cmd_mix, capture_output=True)
        else:
            generator.mix_audio(temp_video, front_path, music_path, final_video, 
                                mix_music_ratio=mix_music_ratio, mix_bg_ratio=mix_bg_ratio)
            
        update_job(status="done", progress=1.0, log_line="Highlight video creation finished successfully!", result=final_video)
        
    except Exception as e:
        traceback.print_exc()
        update_job(status="error", log_line=f"Error occurred: {str(e)}", error=e)
        
    finally:
        # Clean up temp files
        if os.path.exists(temp_video):
            try: os.remove(temp_video)
            except: pass
        if is_temp:
            if video_front and os.path.exists(video_front):
                try: os.remove(video_front)
                except: pass
            if video_rear and os.path.exists(video_rear):
                try: os.remove(video_rear)
                except: pass
            update_job(log_line="Cleaned up temporary demuxed tracks.")

@app.post("/api/generate-highlights")
def generate_highlights(
    front_path: str = Form(...),
    rear_path: str = Form(...),
    music_path: str = Form(None),
    duration: float = Form(300.0),
    p_rider: float = Form(0.2),
    p_kite: float = Form(0.3),
    p_scenery: float = Form(0.5),
    format_type: str = Form("YT"),
    mix_music_ratio: float = Form(0.7),
    mix_bg_ratio: float = Form(0.3),
    is_preview: bool = Form(False)
):
    global job_state
    
    with job_lock:
        if job_state["status"] in ["scanning", "rendering", "mixing"]:
            raise HTTPException(status_code=400, detail="A rendering job is already running.")
            
        # Reset job state
        job_state = {
            "status": "idle",
            "progress": 0.0,
            "log": "",
            "error_message": "",
            "result_video": ""
        }
        
    # Start background thread
    t = threading.Thread(
        target=bg_process_highlights,
        args=(front_path, rear_path, music_path, duration, 
              p_rider, p_kite, p_scenery, format_type, 
              mix_music_ratio, mix_bg_ratio, is_preview)
    )
    t.start()
    
    return {"message": "Job started successfully."}

@app.get("/api/job-status")
def get_job_status():
    with job_lock:
        return JSONResponse(content=job_state)

@app.get("/api/play-video")
def play_video():
    """
    Serves the generated video file.
    """
    video_path = "final_output.mp4"
    if os.path.exists(video_path):
        return FileResponse(video_path, media_type="video/mp4")
    raise HTTPException(status_code=404, detail="Result video not found. Run a generation first.")

# Serve GUI static directory
gui_dir = os.path.join(os.path.dirname(__file__), "gui")
if os.path.exists(gui_dir):
    app.mount("/gui", StaticFiles(directory=gui_dir), name="gui")

@app.get("/", response_class=HTMLResponse)
def read_root():
    # If gui/index.html exists, return it, otherwise return a default page
    gui_index = os.path.join(gui_dir, "index.html")
    if os.path.exists(gui_index):
        with open(gui_index, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Server Running</h1><p>GUI directory is empty. Create HTML files inside gui/.</p>")

if __name__ == "__main__":
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
