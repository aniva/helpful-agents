import os
import glob
import subprocess
import shutil
import re
from cutter import check_nvenc_available

import cutter

FADE_DURATION = 0.35

def get_video_duration(path):
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path
    ]
    try:
        out = subprocess.check_output(cmd, text=True).strip()
        return float(out)
    except Exception:
        return 0.0

def stitch_highlights(dest_dir, attempt_files=None, output_filename="PumpFoil_Highlights.mp4", progress_callback=None, benchmark=None):
    """
    Stitches attempt clips together with smooth dip-fade transitions.
    Reports frame-by-frame progress and handles graceful cancellation.
    """
    attempts_dir = os.path.join(dest_dir, "attempts")
    temp_dir = os.path.join(dest_dir, ".temp_faded")
    os.makedirs(temp_dir, exist_ok=True)
    out_file = os.path.join(dest_dir, output_filename)

    if not attempt_files:
        # Auto-discover attempt clips and sort numerically
        pattern = re.compile(r"^Attempt_(\d+)_", re.IGNORECASE)
        attempt_files = glob.glob(os.path.join(attempts_dir, "Attempt_*.mp4"))
        attempt_files.sort(key=lambda f: int(pattern.search(os.path.basename(f)).group(1)) if pattern.search(os.path.basename(f)) else 9999)

    if len(attempt_files) == 0:
        return {"error": "No attempt clips found to stitch highlights."}

    if len(attempt_files) == 1:
        single_file = attempt_files[0]
        try:
            shutil.copy2(single_file, out_file)
            total_dur = get_video_duration(out_file)
            return {
                "status": "ok",
                "outputFile": out_file,
                "filename": os.path.basename(out_file),
                "clipCount": 1,
                "duration": total_dur
            }
        except Exception as e:
            return {"error": f"Failed copying single attempt clip: {e}"}

    has_nvenc = check_nvenc_available()
    speed_factor = (benchmark.get("speed", 0.8) if benchmark else 0.8) if has_nvenc else 0.25
    faded_clips = []

    # Calculate total duration for fading
    durations = [get_video_duration(f) for f in attempt_files]
    total_fading_duration = sum(durations)
    elapsed_fading_seconds_done = 0.0

    for idx, fpath in enumerate(attempt_files, 1):
        if cutter.is_cancelled:
            shutil.rmtree(temp_dir, ignore_errors=True)
            return {"status": "cancelled", "error": "Operation cancelled by user."}

        base = os.path.splitext(os.path.basename(fpath))[0]
        out_faded = os.path.join(temp_dir, f"fade_{base}.mp4")
        dur = durations[idx - 1]
        fade_out_start = max(0, dur - FADE_DURATION)

        if has_nvenc:
            cmd = [
                "ffmpeg", "-y",
                "-hwaccel", "cuda",
                "-i", fpath,
                "-vf", f"fade=t=in:st=0:d={FADE_DURATION},fade=t=out:st={fade_out_start:.3f}:d={FADE_DURATION},format=yuv420p",
                "-af", f"afade=t=in:st=0:d={FADE_DURATION},afade=t=out:st={fade_out_start:.3f}:d={FADE_DURATION}",
                "-c:v", "hevc_nvenc",
                "-preset", "p4",
                "-cq", "19",
                "-c:a", "aac",
                "-b:a", "192k",
                "-progress", "pipe:1",
                out_faded
            ]
        else:
            cmd = [
                "ffmpeg", "-y",
                "-i", fpath,
                "-vf", f"fade=t=in:st=0:d={FADE_DURATION},fade=t=out:st={fade_out_start:.3f}:d={FADE_DURATION},format=yuv420p",
                "-af", f"afade=t=in:st=0:d={FADE_DURATION},afade=t=out:st={fade_out_start:.3f}:d={FADE_DURATION}",
                "-c:v", "libx265",
                "-preset", "veryfast",
                "-crf", "20",
                "-c:a", "aac",
                "-b:a", "192k",
                "-progress", "pipe:1",
                out_faded
            ]

        try:
            cutter.current_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1
            )
        except Exception as e:
            print(f"Error launching fade for {base}: {e}")
            continue

        clip_rendered_sec = 0.0
        import time
        last_report_time = 0.0

        if cutter.current_process.stdout:
            for line in cutter.current_process.stdout:
                if cutter.is_cancelled:
                    break
                line = line.strip()
                if line.startswith("out_time_ms="):
                    try:
                        ms = int(line.split("=")[1])
                        clip_rendered_sec = max(0.0, ms / 1000000.0)
                    except Exception:
                        pass
                elif line.startswith("progress=") and line == "progress=end":
                    clip_rendered_sec = dur

                now = time.time()
                if now - last_report_time >= 0.1 and progress_callback:
                    last_report_time = now
                    current_overall = elapsed_fading_seconds_done + min(dur, clip_rendered_sec)
                    overall_fading_pct = (current_overall / max(0.1, total_fading_duration)) if total_fading_duration > 0 else 0
                    
                    rem_sec = max(0.0, total_fading_duration - current_overall)
                    eta_sec = int(rem_sec / max(0.1, speed_factor))
                    eta_str = f"{eta_sec}s remaining" if eta_sec < 60 else f"{eta_sec // 60}m {eta_sec % 60}s remaining"

                    clip_pct = int(min(100, (clip_rendered_sec / max(0.1, dur)) * 100))
                    msg = f"Stitching Transition {idx}/{len(attempt_files)}: {base} ({clip_pct}%) &bull; ETA: {eta_str}"
                    details = f"Applying dip-fade in/out ({dur:.1f}s) &bull; {eta_str}"

                    progress_callback(
                        idx=idx,
                        total=len(attempt_files),
                        pct=int(overall_fading_pct * 100),
                        msg=msg,
                        details=details,
                        eta=eta_str
                    )

        cutter.current_process.wait()
        returncode = cutter.current_process.returncode
        cutter.current_process = None

        if cutter.is_cancelled:
            shutil.rmtree(temp_dir, ignore_errors=True)
            return {"status": "cancelled", "error": "Operation cancelled by user."}

        if returncode == 0:
            elapsed_fading_seconds_done += dur
            faded_clips.append(out_faded)
        else:
            print(f"Error fading {base}: code {returncode}")

    if not faded_clips:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return {"error": "Failed to apply transitions to clips."}

    # Concat
    concat_txt = os.path.join(temp_dir, "concat.txt")
    with open(concat_txt, "w", encoding="utf-8") as f:
        for c in faded_clips:
            f.write(f"file '{c.replace(chr(92), '/')}'\n")

    cmd_concat = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", concat_txt,
        "-c", "copy",
        out_file
    ]
    try:
        cutter.current_process = subprocess.Popen(cmd_concat, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        cutter.current_process.wait()
        res_code = cutter.current_process.returncode
        cutter.current_process = None
    except Exception as e:
        res_code = 1

    shutil.rmtree(temp_dir, ignore_errors=True)

    if cutter.is_cancelled:
        if os.path.exists(out_file):
            try: os.remove(out_file)
            except Exception: pass
        return {"status": "cancelled", "error": "Operation cancelled by user."}

    if res_code == 0:
        total_dur = get_video_duration(out_file)
        return {
            "status": "ok",
            "outputFile": out_file,
            "filename": os.path.basename(out_file),
            "clipCount": len(faded_clips),
            "duration": total_dur
        }
    else:
        return {"error": f"Concat failed (exit code {res_code})"}