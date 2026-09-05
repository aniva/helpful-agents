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

if __name__ == "__main__":
    print("Detected GoPro paths:", detect_gopro())
    print("Suggested Destination:", suggest_destination())