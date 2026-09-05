import os
import glob
import subprocess
import shutil
import re
from cutter import check_nvenc_available

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

def stitch_highlights(dest_dir, attempt_files=None, output_filename="PumpFoil_Highlights.mp4", progress_callback=None):
    """
    Stitches attempt clips together with smooth dip-fade transitions.
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
        # Single attempt: copy or produce the output highlight directly
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
    faded_clips = []

    for idx, fpath in enumerate(attempt_files, 1):
        base = os.path.splitext(os.path.basename(fpath))[0]
        out_faded = os.path.join(temp_dir, f"fade_{base}.mp4")
        dur = get_video_duration(fpath)
        fade_out_start = max(0, dur - FADE_DURATION)

        if progress_callback:
            progress_callback(idx, len(attempt_files), f"Applying transitions: {base} ({dur:.1f}s)...")

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
                out_faded
            ]

        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        if res.returncode == 0:
            faded_clips.append(out_faded)
        else:
            print(f"Error fading {base}: {res.stderr[-200:]}")

    if not faded_clips:
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
    res_concat = subprocess.run(cmd_concat, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    shutil.rmtree(temp_dir, ignore_errors=True)

    if res_concat.returncode == 0:
        total_dur = get_video_duration(out_file)
        return {
            "status": "ok",
            "outputFile": out_file,
            "filename": os.path.basename(out_file),
            "clipCount": len(faded_clips),
            "duration": total_dur
        }
    else:
        return {"error": f"Concat failed: {res_concat.stderr[-200:]}"}