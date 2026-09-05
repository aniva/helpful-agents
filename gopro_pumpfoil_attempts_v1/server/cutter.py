import os
import subprocess
import json

# Global process tracking for graceful cancellation
current_process = None
is_cancelled = False

def cancel_active_process():
    """Cancels any running ffmpeg subprocess cleanly."""
    global current_process, is_cancelled
    is_cancelled = True
    if current_process:
        try:
            current_process.terminate()
            current_process.kill()
        except Exception:
            pass
        current_process = None

def check_nvenc_available():
    try:
        res = subprocess.run(["ffmpeg", "-encoders"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return "hevc_nvenc" in res.stdout
    except Exception:
        return False

def parse_time_str(t_str):
    """Parses MM:SS or HH:MM:SS string to total seconds."""
    parts = str(t_str).strip().split(":")
    try:
        if len(parts) == 2:
            return float(parts[0]) * 60 + float(parts[1])
        elif len(parts) == 3:
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    except Exception:
        pass
    return 0.0

def cut_attempts(source_dir, dest_dir, cuts, progress_callback=None, benchmark=None):
    """
    Renders each marked attempt into dest_dir/attempts/ using GPU NVENC (or CPU fallback)
    with clean IDR keyframes starting at frame 0.
    Reports smooth frame-by-frame progress and estimated time remaining.
    """
    global current_process, is_cancelled
    is_cancelled = False
    current_process = None

    attempts_dir = os.path.join(dest_dir, "attempts")
    os.makedirs(attempts_dir, exist_ok=True)

    has_nvenc = check_nvenc_available()
    speed_factor = (benchmark.get("speed", 0.8) if benchmark else 0.8) if has_nvenc else 0.25
    fps_est = (benchmark.get("fps", 48.0) if benchmark else 48.0) if has_nvenc else 15.0

    valid_cuts = []
    for c in cuts:
        s = parse_time_str(c.get("startTime", "00:00"))
        e = parse_time_str(c.get("stopTime", "00:00"))
        if e > s:
            valid_cuts.append((c, s, e, e - s))

    total_cut_duration = sum(d for _, _, _, d in valid_cuts)
    elapsed_total_seconds_done = 0.0
    results = []

    for idx, (cut, s_sec, e_sec, clip_dur) in enumerate(valid_cuts, 1):
        if is_cancelled:
            results.append({"status": "cancelled", "label": cut.get("label")})
            break

        clip_name = cut.get("clipName")
        start_time = cut.get("startTime", "00:00")
        stop_time = cut.get("stopTime", "00:00")
        label = cut.get("label", f"Attempt_{idx}").strip().replace(" ", "_")

        in_file = os.path.join(source_dir, clip_name)
        clean_start = start_time.replace(":", "-")
        clean_stop = stop_time.replace(":", "-")
        out_name = f"{label}_{clip_name}_{clean_start}-{clean_stop}.mp4"
        out_file = os.path.join(attempts_dir, out_name)

        if has_nvenc:
            cmd = [
                "ffmpeg", "-y",
                "-hwaccel", "cuda",
                "-ss", start_time,
                "-to", stop_time,
                "-i", in_file,
                "-c:v", "hevc_nvenc",
                "-preset", "p4",
                "-cq", "19",
                "-c:a", "copy",
                "-progress", "pipe:1",
                out_file
            ]
        else:
            cmd = [
                "ffmpeg", "-y",
                "-ss", start_time,
                "-to", stop_time,
                "-i", in_file,
                "-c:v", "libx265",
                "-crf", "20",
                "-preset", "veryfast",
                "-c:a", "copy",
                "-progress", "pipe:1",
                out_file
            ]

        try:
            import time
            current_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1
            )
        except Exception as e:
            results.append({"status": "error", "file": out_name, "error": str(e)})
            continue

        clip_rendered_sec = 0.0
        last_report_time = 0.0

        if current_process.stdout:
            for line in current_process.stdout:
                if is_cancelled:
                    break
                line = line.strip()
                if line.startswith("out_time_ms="):
                    try:
                        ms = int(line.split("=")[1])
                        clip_rendered_sec = max(0.0, ms / 1000000.0)
                    except Exception:
                        pass
                elif line.startswith("progress=") and line == "progress=end":
                    clip_rendered_sec = clip_dur

                now = time.time()
                if now - last_report_time >= 0.1 and progress_callback:
                    last_report_time = now
                    current_overall_rendered = elapsed_total_seconds_done + min(clip_dur, clip_rendered_sec)
                    overall_pct = (current_overall_rendered / max(0.1, total_cut_duration)) if total_cut_duration > 0 else 0
                    
                    rem_video_sec = max(0.0, total_cut_duration - current_overall_rendered)
                    eta_sec = int(rem_video_sec / max(0.1, speed_factor))
                    eta_str = f"{eta_sec}s remaining" if eta_sec < 60 else f"{eta_sec // 60}m {eta_sec % 60}s remaining"

                    current_clip_pct = int(min(100, (clip_rendered_sec / max(0.1, clip_dur)) * 100))
                    msg = f"Cutting Attempt {idx}/{len(valid_cuts)}: {label} ({current_clip_pct}%) &bull; ETA: {eta_str}"
                    details = f"Rendering {clean_start} to {clean_stop} ({clip_dur:.1f}s) via {'GPU NVENC' if has_nvenc else 'CPU'} @ {fps_est:.0f} fps"
                    
                    progress_callback(
                        idx=idx,
                        total=len(valid_cuts),
                        pct=int(overall_pct * 100),
                        msg=msg,
                        details=details,
                        eta=eta_str
                    )

        current_process.wait()
        returncode = current_process.returncode
        current_process = None

        if is_cancelled:
            if os.path.exists(out_file):
                try: os.remove(out_file)
                except Exception: pass
            results.append({"status": "cancelled", "label": label})
            break

        if returncode == 0:
            elapsed_total_seconds_done += clip_dur
            results.append({"status": "success", "file": out_name, "path": out_file, "label": label})
        else:
            results.append({"status": "error", "file": out_name, "error": f"ffmpeg exit code {returncode}"})

    return results

def sync_cuts_file(dest_dir, cuts, source_dir=None):
    """Saves the current cuts list to cuts.txt in the destination directory and mirrors to source SD card."""
    os.makedirs(dest_dir, exist_ok=True)
    cuts_file = os.path.join(dest_dir, "cuts.txt")
    lines = [
        "# Pump Foil Cut List",
        "# SourceFile, StartTime, StopTime, Label"
    ]
    for idx, c in enumerate(cuts, 1):
        clip = c.get("clipName")
        st = c.get("startTime")
        et = c.get("stopTime")
        lbl = c.get("label", f"Attempt_{idx}").strip().replace(" ", "_")
        lines.append(f"{clip}, {st}, {et}, {lbl}")
    
    with open(cuts_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    # Mirror to SD card if source_dir provided
    if source_dir:
        try:
            from detector import mirror_cuts_to_sd, save_sd_metadata
            mirror_cuts_to_sd(source_dir, cuts)
            save_sd_metadata(source_dir, dest_dir, {"cutCount": len(cuts)})
        except Exception as e:
            print(f"Warning: Could not mirror to SD: {e}")

    return cuts_file