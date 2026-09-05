import os
import subprocess
import json

def check_nvenc_available():
    try:
        res = subprocess.run(["ffmpeg", "-encoders"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return "hevc_nvenc" in res.stdout
    except Exception:
        return False

def cut_attempts(source_dir, dest_dir, cuts, progress_callback=None):
    """
    Renders each marked attempt into dest_dir/attempts/ using GPU NVENC (or CPU fallback)
    with clean IDR keyframes starting at frame 0.
    """
    attempts_dir = os.path.join(dest_dir, "attempts")
    os.makedirs(attempts_dir, exist_ok=True)

    has_nvenc = check_nvenc_available()
    results = []

    for idx, cut in enumerate(cuts, 1):
        clip_name = cut.get("clipName")
        start_time = cut.get("startTime")
        stop_time = cut.get("stopTime")
        label = cut.get("label", f"Attempt_{idx}").strip().replace(" ", "_")

        in_file = os.path.join(source_dir, clip_name)
        clean_start = start_time.replace(":", "-")
        clean_stop = stop_time.replace(":", "-")
        out_name = f"{label}_{clip_name}_{clean_start}-{clean_stop}.mp4"
        out_file = os.path.join(attempts_dir, out_name)

        if progress_callback:
            progress_callback(idx, len(cuts), f"Rendering {label} ({clean_start} - {clean_stop})...")

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
                out_file
            ]
        else:
            # CPU fallback
            cmd = [
                "ffmpeg", "-y",
                "-ss", start_time,
                "-to", stop_time,
                "-i", in_file,
                "-c:v", "libx265",
                "-crf", "20",
                "-preset", "veryfast",
                "-c:a", "copy",
                out_file
            ]

        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        if res.returncode == 0:
            results.append({"status": "success", "file": out_name, "path": out_file, "label": label})
        else:
            results.append({"status": "error", "file": out_name, "error": res.stderr[-200:]})

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