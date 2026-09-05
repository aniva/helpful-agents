import os
import sys
import glob
from datetime import datetime

def is_windows():
    return sys.platform.startswith("win")

def is_wsl():
    if sys.platform.startswith("linux"):
        try:
            with open("/proc/version", "r") as f:
                return "microsoft" in f.read().lower()
        except Exception:
            return False
    return False

def to_local_path(p):
    """Normalizes path for current OS environment (Windows vs Linux/WSL)."""
    if not p:
        return ""
    p = p.strip()
    if is_windows():
        # If /mnt/c/... convert to C:\...
        if p.startswith("/mnt/"):
            parts = p.split("/")
            if len(parts) >= 3 and len(parts[2]) == 1:
                drive = parts[2].upper()
                rest = "\\".join(parts[3:])
                return f"{drive}:\\{rest}"
        return os.path.normpath(p)
    else:
        # If C:\... convert to /mnt/c/...
        if len(p) >= 2 and p[1] == ":":
            drive = p[0].lower()
            rest = p[2:].replace("\\", "/").lstrip("/")
            return f"/mnt/{drive}/{rest}"
        return os.path.normpath(p)

def detect_gopro():
    """Finds GoPro SD card directories with DCIM/100GOPRO."""
    detected = []
    
    if is_windows():
        import string
        for letter in string.ascii_uppercase:
            root = f"{letter}:\\"
            if not os.path.exists(root):
                continue
            cand1 = os.path.join(root, "DCIM", "100GOPRO")
            cand2 = os.path.join(root, "DCIM")
            if os.path.exists(cand1) and glob.glob(os.path.join(cand1, "*.MP4")):
                detected.append(cand1)
            elif os.path.exists(cand2):
                gopro_folders = glob.glob(os.path.join(cand2, "*GOPRO*"))
                for gf in gopro_folders:
                    if glob.glob(os.path.join(gf, "*.MP4")):
                        detected.append(gf)
    else:
        # Linux / WSL
        mnt_roots = ["/mnt", "/media", "/run/media"]
        for mroot in mnt_roots:
            if not os.path.exists(mroot):
                continue
            for item in glob.glob(os.path.join(mroot, "*", "DCIM", "*GOPRO*")):
                if glob.glob(os.path.join(item, "*.MP4")):
                    detected.append(item)

    return detected

def suggest_destination(source_dir=None):
    """
    Suggests an appropriate destination directory on a fast secondary drive (e.g. E:).
    Folder name format: GOPRO_<recording date>_<first recording start time>
    e.g. GOPRO_20260627_1009
    """
    folder_name = None

    if source_dir:
        src_path = to_local_path(source_dir)
        if os.path.exists(src_path):
            all_mp4 = glob.glob(os.path.join(src_path, "*.MP4")) + glob.glob(os.path.join(src_path, "*.mp4"))
            # remove duplicates
            seen = set()
            unique_mp4 = []
            for f in all_mp4:
                nc = os.path.normcase(os.path.abspath(f))
                if nc not in seen:
                    seen.add(nc)
                    unique_mp4.append(f)

            if unique_mp4:
                # Find earliest recording session
                try:
                    from server.extractor import parse_gopro_filename, get_video_duration
                except ImportError:
                    from extractor import parse_gopro_filename, get_video_duration
                raw_clips = []
                for f in unique_mp4:
                    raw_s, ch = parse_gopro_filename(f)
                    try:
                        mtime = os.path.getmtime(f)
                    except Exception:
                        mtime = 0.0
                    raw_clips.append({"file": f, "raw_s": raw_s, "ch": ch, "mtime": mtime})

                session_groups = {}
                for c in raw_clips:
                    session_groups.setdefault(c["raw_s"], []).append(c)

                sorted_sessions = []
                for rs, group in session_groups.items():
                    group.sort(key=lambda x: x["ch"])
                    earliest_time = min(x["mtime"] for x in group)
                    sorted_sessions.append({"raw_s": rs, "earliest_time": earliest_time, "first_clip": group[0]})

                sorted_sessions.sort(key=lambda s: (s["earliest_time"], s["raw_s"]))
                first_clip_info = sorted_sessions[0]["first_clip"]
                first_file = first_clip_info["file"]
                mtime = first_clip_info["mtime"]
                dur = get_video_duration(first_file)
                # Recording start time = modification time minus duration
                start_epoch = max(0.0, mtime - dur) if mtime > 0 else 0.0
                if start_epoch > 0:
                    dt = datetime.fromtimestamp(start_epoch)
                    rec_date = dt.strftime("%Y%m%d")
                    rec_time = dt.strftime("%H%M")
                    folder_name = f"GOPRO_{rec_date}_{rec_time}"

    if not folder_name:
        now = datetime.now()
        folder_name = f"GOPRO_{now.strftime('%Y%m%d')}_{now.strftime('%H%M')}"

    if is_windows():
        for d in ["E:\\", "D:\\", os.path.expanduser("~\\Videos")]:
            if os.path.exists(d):
                return os.path.join(d, folder_name)
    else:
        for d in ["/mnt/e", "/mnt/d", os.path.expanduser("~/Videos")]:
            if os.path.exists(d):
                return os.path.join(d, folder_name)
    
    return os.path.join(os.path.expanduser("~"), folder_name)

# SD Card Metadata & Cuts Persistence
METADATA_FILENAME = ".pumpfoil_session.json"
CUTS_FILENAME = "cuts.txt"

def get_sd_metadata_path(source_dir):
    return os.path.join(to_local_path(source_dir), METADATA_FILENAME)

def get_sd_cuts_path(source_dir):
    return os.path.join(to_local_path(source_dir), CUTS_FILENAME)

def save_sd_metadata(source_dir, dest_dir, extra_data=None):
    """Saves session linkage and metadata to the GoPro directory on the SD card."""
    sd_path = to_local_path(source_dir)
    if not os.path.exists(sd_path):
        return False
    meta_file = get_sd_metadata_path(source_dir)
    payload = {
        "sourceDir": source_dir,
        "destDir": dest_dir,
        "updatedAt": datetime.now().isoformat(),
    }
    if extra_data and isinstance(extra_data, dict):
        payload.update(extra_data)
    try:
        import json
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        return True
    except Exception as e:
        print(f"Warning: Could not save SD metadata: {e}")
        return False

def load_sd_metadata(source_dir):
    """Reads session metadata from the SD card if present."""
    meta_file = get_sd_metadata_path(source_dir)
    if os.path.exists(meta_file):
        try:
            import json
            with open(meta_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None

def mirror_cuts_to_sd(source_dir, cuts):
    """Mirrors cuts.txt directly onto the SD card in the GoPro directory."""
    sd_path = to_local_path(source_dir)
    if not os.path.exists(sd_path):
        return False
    sd_cuts_file = get_sd_cuts_path(source_dir)
    lines = [
        "# Pump Foil Cut List (SD Card Mirror)",
        "# SourceFile, StartTime, StopTime, Label"
    ]
    for idx, c in enumerate(cuts, 1):
        clip = c.get("clipName")
        st = c.get("startTime")
        et = c.get("stopTime")
        lbl = c.get("label", f"Attempt_{idx}").strip().replace(" ", "_")
        lines.append(f"{clip}, {st}, {et}, {lbl}")
    try:
        with open(sd_cuts_file, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return True
    except Exception as e:
        print(f"Warning: Could not mirror cuts to SD: {e}")
        return False

def load_sd_cuts(source_dir):
    """Reads cuts.txt from the SD card and parses into cuts objects."""
    sd_cuts_file = get_sd_cuts_path(source_dir)
    if not os.path.exists(sd_cuts_file):
        return []
    cuts = []
    try:
        with open(sd_cuts_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 3:
                    clip = parts[0]
                    st = parts[1]
                    et = parts[2]
                    lbl = parts[3] if len(parts) >= 4 else f"Attempt_{len(cuts) + 1}"
                    # calculate seconds
                    def parse_t(tstr):
                        p = tstr.split(":")
                        if len(p) == 2:
                            return int(p[0]) * 60 + float(p[1])
                        elif len(p) == 3:
                            return int(p[0]) * 3600 + int(p[1]) * 60 + float(p[2])
                        return float(tstr)
                    start_sec = parse_t(st)
                    stop_sec = parse_t(et)
                    cuts.append({
                        "id": int(datetime.now().timestamp() * 1000) + len(cuts),
                        "clipName": clip,
                        "startSec": round(start_sec, 2),
                        "stopSec": round(stop_sec, 2),
                        "startTime": st,
                        "stopTime": et,
                        "duration": max(1, round(stop_sec - start_sec)),
                        "label": lbl
                    })
        return cuts
    except Exception as e:
        print(f"Warning: Could not read SD cuts: {e}")
        return []

def delete_sd_cuts(source_dir):
    """Deletes cuts.txt and removes cuts references from SD card metadata."""
    sd_cuts_file = get_sd_cuts_path(source_dir)
    if os.path.exists(sd_cuts_file):
        try:
            os.remove(sd_cuts_file)
        except Exception:
            pass
    meta_file = get_sd_metadata_path(source_dir)
    if os.path.exists(meta_file):
        try:
            import json
            with open(meta_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "cuts" in data:
                del data["cuts"]
            with open(meta_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass
    return True

def benchmark_hardware():
    """
    Benchmarks encoding speed for 1 second of 4K 60fps video.
    Returns hardware type, measured FPS, and speed factor.
    """
    import subprocess
    import time
    from cutter import check_nvenc_available

    has_nvenc = check_nvenc_available()
    codec = "hevc_nvenc" if has_nvenc else "libx265"
    preset = ["-preset", "p4", "-cq", "19"] if has_nvenc else ["-preset", "veryfast", "-crf", "20"]

    t0 = time.time()
    cmd = [
        "ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=1:size=3840x2160:rate=60",
        "-c:v", codec, *preset, "-f", "null", "-"
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        elapsed = max(0.01, time.time() - t0)
        fps = 60.0 / elapsed
        speed = fps / 60.0
        return {
            "hardware": "GPU NVENC (NVIDIA CUDA)" if has_nvenc else "CPU (libx265)",
            "codec": codec,
            "hasNvenc": has_nvenc,
            "fps": round(fps, 1),
            "speed": round(speed, 2),
            "benchmarkSeconds": round(elapsed, 2)
        }
    except Exception as e:
        return {
            "hardware": "GPU NVENC" if has_nvenc else "CPU",
            "codec": codec,
            "hasNvenc": has_nvenc,
            "fps": 45.0 if has_nvenc else 15.0,
            "speed": 0.75 if has_nvenc else 0.25,
            "error": str(e)
        }

if __name__ == "__main__":
    print("Detected GoPro paths:", detect_gopro())
    print("Suggested Destination:", suggest_destination())