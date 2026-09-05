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
    """Suggests an appropriate destination directory on a fast secondary drive (e.g. E:)."""
    today_str = datetime.now().strftime("%Y%m%d")
    folder_name = f"{today_str}_PumpFoil"

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

if __name__ == "__main__":
    print("Detected GoPro paths:", detect_gopro())
    print("Suggested Destination:", suggest_destination())