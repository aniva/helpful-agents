import os
import glob
import subprocess
import json
import math
import re
from datetime import datetime

def parse_gopro_filename(filename):
    """
    Extracts (raw_session_id, chapter_number) from GoPro filenames.
    e.g. GX015264.MP4 -> (5264, 1)
         GX025265.MP4 -> (5265, 2)
         GOPR0012.MP4 -> (12, 0)
    """
    base = os.path.splitext(os.path.basename(filename))[0]
    m = re.match(r"^G[XHLP](\d{2})(\d{4})$", base, re.IGNORECASE)
    if m:
        return int(m.group(2)), int(m.group(1))
    m2 = re.match(r"^GOPR(\d{4})$", base, re.IGNORECASE)
    if m2:
        return int(m2.group(1)), 0
    try:
        mtime = int(os.path.getmtime(filename))
        return mtime, 0
    except Exception:
        return 999999, 0

def format_time_str(seconds):
    s = int(round(seconds))
    m = s // 60
    rem = s % 60
    return f"{m:02d}:{rem:02d}"

def get_video_duration(video_path):
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path
    ]
    try:
        out = subprocess.check_output(cmd, text=True).strip()
        return float(out)
    except Exception:
        return 0.0

def scan_and_extract_timeline(source_dir, dest_dir, interval=4.0, reuse_thumbnails=True, progress_callback=None):
    os.makedirs(dest_dir, exist_ok=True)
    thumb_base_dir = os.path.join(dest_dir, f".thumbnails_{int(interval)}s")
    os.makedirs(thumb_base_dir, exist_ok=True)

    all_found = glob.glob(os.path.join(source_dir, "*.MP4")) + glob.glob(os.path.join(source_dir, "*.mp4"))
    seen_bases = set()
    mp4_files = []
    for f in all_found:
        norm = os.path.normcase(os.path.abspath(f))
        if norm not in seen_bases:
            seen_bases.add(norm)
            mp4_files.append(f)
    
    if not mp4_files:
        return {"error": f"No MP4 video files found in {source_dir}"}

    # Gather info for all valid clips
    raw_clips = []
    if progress_callback:
        progress_callback(1, "Inspecting GoPro files...", "Reading clip metadata...")

    for mp4 in mp4_files:
        base = os.path.splitext(os.path.basename(mp4))[0]
        raw_session, chapter = parse_gopro_filename(mp4)

        lrv_name = "GL" + base[2:] + ".LRV"
        lrv_path = os.path.join(source_dir, lrv_name)
        if not os.path.exists(lrv_path):
            lrv_name_lower = "gl" + base[2:] + ".lrv"
            lrv_path = os.path.join(source_dir, lrv_name_lower)
        
        src_video = lrv_path if os.path.exists(lrv_path) else mp4
        dur = get_video_duration(src_video)
        if dur < 3.0:
            continue

        try:
            mtime = os.path.getmtime(mp4)
        except Exception:
            mtime = 0.0

        raw_clips.append({
            "mp4": mp4,
            "base": base,
            "raw_session": raw_session,
            "chapter": chapter,
            "src_video": src_video,
            "dur": dur,
            "mtime": mtime
        })

    if not raw_clips:
        return {"error": "No valid clips found."}

    # Group clips by raw GoPro session ID
    session_groups = {}
    for c in raw_clips:
        rs = c["raw_session"]
        session_groups.setdefault(rs, []).append(c)

    # Sort groups chronologically by the earliest clip's timestamp / chapter 1
    sorted_sessions = []
    for rs, group in session_groups.items():
        # sort within group by chapter number
        group.sort(key=lambda x: x["chapter"])
        earliest_time = min(x["mtime"] for x in group)
        sorted_sessions.append({
            "raw_session": rs,
            "earliest_time": earliest_time,
            "clips": group
        })
    sorted_sessions.sort(key=lambda s: (s["earliest_time"], s["raw_session"]))

    # Flatten into ordered list of clips with sequential 1-based sessionIndex
    clip_infos = []
    for session_idx, sdata in enumerate(sorted_sessions, 1):
        for c in sdata["clips"]:
            c["sessionIndex"] = session_idx
            clip_infos.append(c)

    total_session_dur = max(1.0, sum(c["dur"] for c in clip_infos))
    clips = []
    processed_dur = 0.0
    global_time = 0.0
    total_frames = 0
    total_clips = len(clip_infos)

    for c_idx, cinfo in enumerate(clip_infos, 1):
        base = cinfo["base"]
        dur = cinfo["dur"]
        src_video = cinfo["src_video"]
        raw_session = cinfo["raw_session"]
        chapter = cinfo["chapter"]
        session_index = cinfo["sessionIndex"]
        mp4 = cinfo["mp4"]

        clip_thumb_dir = os.path.join(thumb_base_dir, base)
        os.makedirs(clip_thumb_dir, exist_ok=True)

        expected_count = max(1, math.floor(dur / interval))
        existing_thumbs = sorted(glob.glob(os.path.join(clip_thumb_dir, "thumb_*.jpg")))

        # If user chose NOT to reuse thumbnails, remove old ones
        if not reuse_thumbnails and existing_thumbs:
            for old_t in existing_thumbs:
                try:
                    os.remove(old_t)
                except Exception:
                    pass
            existing_thumbs = []

        if len(existing_thumbs) < expected_count - 1:
            cmd = [
                "ffmpeg", "-y",
                "-i", src_video,
                "-progress", "pipe:1",
                "-vf", f"fps=1/{interval},scale=240:135",
                "-q:v", "5",
                os.path.join(clip_thumb_dir, "thumb_%04d.jpg")
            ]
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
            frame_cnt = 0

            for line in proc.stdout:
                line = line.strip()
                if line.startswith("out_time_us="):
                    try:
                        us = int(line.split("=")[1])
                        curr_sec = us / 1000000.0
                        overall_sec = processed_dur + min(curr_sec, dur)
                        pct = min(99, int((overall_sec / total_session_dur) * 100))
                        if progress_callback:
                            progress_callback(
                                pct,
                                f"Clip {c_idx} of {total_clips}: {base} ({format_time_str(dur)})",
                                f"{int(curr_sec)}s / {int(dur)}s processed ({frame_cnt} frames extracted)"
                            )
                    except Exception:
                        pass
                elif line.startswith("frame="):
                    try:
                        frame_cnt = int(line.split("=")[1])
                    except Exception:
                        pass

            proc.wait()
            existing_thumbs = sorted(glob.glob(os.path.join(clip_thumb_dir, "thumb_*.jpg")))

        processed_dur += dur
        pct = min(99, int((processed_dur / total_session_dur) * 100))
        if progress_callback:
            progress_callback(pct, f"Clip {c_idx} of {total_clips}: {base} completed", f"{len(existing_thumbs)} frames cached")

        frame_objs = []
        for idx, tpath in enumerate(existing_thumbs):
            sec = idx * interval
            frame_objs.append({
                "index": idx,
                "file": os.path.basename(tpath),
                "relPath": f".thumbnails_{int(interval)}s/{base}/{os.path.basename(tpath)}",
                "sec": round(sec, 2),
                "timeStr": format_time_str(sec),
                "globalSec": round(global_time + sec, 2)
            })

        clips.append({
            "clipName": os.path.basename(mp4),
            "baseName": base,
            "sessionIndex": session_index,
            "rawSession": raw_session,
            "chapter": chapter,
            "duration": round(dur, 2),
            "durationStr": format_time_str(dur),
            "startOffsetGlobal": round(global_time, 2),
            "frameCount": len(frame_objs),
            "frames": frame_objs
        })

        global_time += dur
        total_frames += len(frame_objs)

    if progress_callback:
        progress_callback(100, "Timeline ready!", f"{len(clips)} clips, {total_frames} frames loaded")

    manifest = {
        "sourceDir": source_dir,
        "destDir": dest_dir,
        "interval": interval,
        "clipCount": len(clips),
        "totalDuration": round(global_time, 2),
        "totalDurationStr": format_time_str(global_time),
        "totalFrames": total_frames,
        "clips": clips
    }

    manifest_path = os.path.join(dest_dir, f"manifest_{int(interval)}s.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    return manifest