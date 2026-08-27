#!/usr/bin/env python3
import os
import sys
import json
import subprocess
import argparse

def parse_args():
    parser = argparse.ArgumentParser(description="Stitch highlights sequentially to prevent GPU memory overflow.")
    parser.add_argument("--video", required=True, help="Input video file path.")
    parser.add_argument("--config", required=True, help="Path to config JSON file or raw JSON string.")
    parser.add_argument("--output", required=True, help="Output video file path.")
    parser.add_argument("--fade-duration", type=float, default=1.0, help="Fade transition duration in seconds.")
    return parser.parse_args()

def translate_path(path):
    if sys.platform != "win32" and ":" in path:
        parts = path.split(":")
        drive = parts[0].lower()
        rest = parts[1].replace("\\", "/")
        if rest.startswith("/"):
            return f"/mnt/{drive}{rest}"
        else:
            return f"/mnt/{drive}/{rest}"
    return path

def main():
    args = parse_args()
    
    video_path = translate_path(args.video)
    output_path = translate_path(args.output)
    
    if not os.path.exists(video_path):
        print(f"Error: Input video not found at {video_path}")
        sys.exit(1)
        
    # Get actual video duration to prevent reading past EOF
    video_duration = None
    try:
        probe_cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path
        ]
        res = subprocess.run(probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode == 0:
            video_duration = float(res.stdout.decode().strip())
            print(f"Detected video duration: {video_duration:.3f} seconds")
    except Exception as e:
        print(f"Warning: Could not check video duration via ffprobe: {e}")

    # Parse config
    try:
        if os.path.exists(args.config):
            with open(args.config, "r") as f:
                segments = json.load(f)
        else:
            segments = json.loads(args.config)
    except Exception as e:
        print(f"Error parsing config JSON: {e}")
        sys.exit(1)
        
    if not segments:
        print("Error: No segments found in config.")
        sys.exit(1)

    # Clip segment boundaries to actual video duration
    if video_duration is not None:
        for seg in segments:
            if seg["start"] > video_duration:
                seg["start"] = video_duration
            if seg["end"] > video_duration:
                seg["end"] = video_duration

    print(f"Processing {len(segments)} segments sequentially...")
    
    # Check if GPU is available
    use_nvenc = False
    try:
        res = subprocess.run(["nvidia-smi"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode == 0:
            use_nvenc = True
            print("NVIDIA GPU detected. Using hardware-accelerated hevc_nvenc...")
    except Exception:
        pass

    # Create temporary directory for slices
    temp_dir = os.path.join(os.path.dirname(output_path), "temp_slices")
    os.makedirs(temp_dir, exist_ok=True)
    
    slice_files = []
    
    # Phase 1: Slice and re-encode each segment individually (low VRAM usage, 1 file at a time)
    for idx, seg in enumerate(segments):
        start = seg["start"]
        duration = seg["end"] - start
        slice_file = os.path.join(temp_dir, f"slice_{idx:03d}.mp4")
        slice_files.append(slice_file)
        
        print(f"\n[1/2] Slicing Segment {idx+1}/{len(segments)}: {start:.1f}s to {seg['end']:.1f}s (duration={duration:.1f}s)...")
        
        cmd = ["ffmpeg", "-y", "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", video_path]
        if use_nvenc:
            cmd.extend([
                "-c:v", "hevc_nvenc",
                "-b:v", "50M",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "192k"
            ])
        else:
            cmd.extend([
                "-c:v", "libx264",
                "-preset", "medium",
                "-crf", "18",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "192k"
            ])
        cmd.append(slice_file)
        
        res = subprocess.run(cmd)
        if res.returncode != 0:
            print(f"Error: Slicing failed on Segment {idx+1}")
            sys.exit(1)

    # Phase 2: Sequentially crossfade slices (low VRAM usage, 2 files at a time)
    T_fade = args.fade_duration
    current_file = slice_files[0]
    current_dur = segments[0]["end"] - segments[0]["start"]
    
    for idx in range(1, len(slice_files)):
        next_file = slice_files[idx]
        next_dur = segments[idx]["end"] - segments[idx]["start"]
        offset = current_dur - T_fade
        
        temp_output = os.path.join(temp_dir, f"stitch_step_{idx:03d}.mp4")
        print(f"\n[2/2] Sequential Stitch {idx}/{len(slice_files)-1}: Crossfading at offset {offset:.2f}s...")
        
        filter_complex = (
            f"[0:v][1:v]xfade=transition=fade:duration={T_fade:.3f}:offset={offset:.3f}[v];"
            f"[0:a][1:a]acrossfade=d={T_fade:.3f}:c1=tri:c2=tri[a]"
        )
        
        cmd = [
            "ffmpeg", "-y",
            "-i", current_file,
            "-i", next_file,
            "-filter_complex", filter_complex,
            "-map", "[v]",
            "-map", "[a]"
        ]
        
        if use_nvenc:
            cmd.extend([
                "-c:v", "hevc_nvenc",
                "-b:v", "50M",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "192k",
                "-max_muxing_queue_size", "9999"
            ])
        else:
            cmd.extend([
                "-c:v", "libx264",
                "-preset", "medium",
                "-crf", "18",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "192k",
                "-max_muxing_queue_size", "9999"
            ])
            
        cmd.append(temp_output)
        
        res = subprocess.run(cmd)
        if res.returncode != 0:
            print(f"Error: Crossfading failed at step {idx}")
            sys.exit(1)
            
        current_file = temp_output
        current_dur = current_dur + next_dur - T_fade

    # Move final output to destination
    if os.path.exists(output_path):
        os.remove(output_path)
    os.rename(current_file, output_path)
    
    # Cleanup temp slices
    print("\nCleaning up temporary files...")
    for f in os.listdir(temp_dir):
        try:
            os.remove(os.path.join(temp_dir, f))
        except Exception:
            pass
    try:
        os.rmdir(temp_dir)
    except Exception:
        pass
        
    print(f"\nStitching completed successfully!")
    print(f"Output saved to: {output_path}")

if __name__ == "__main__":
    main()
