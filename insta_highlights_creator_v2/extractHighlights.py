#!/usr/bin/env python3
import os
import sys
import json
import math
import argparse
import subprocess

def parse_args():
    parser = argparse.ArgumentParser(
        description="Telemetry-driven video highlight extraction from Gyroflow telemetry."
    )
    parser.add_argument(
        "--video",
        required=True,
        help="Path to the stabilized master video file."
    )
    parser.add_argument(
        "--gyroflow",
        help="Path to the .gyroflow project file (optional, if missing we will generate camera.json from --video)."
    )
    parser.add_argument(
        "--output-dir",
        default="outputHighlights",
        help="Output directory to save highlight clips."
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=2.5,
        help="Gyroscope angular velocity magnitude threshold (rad/s) to trigger highlights."
    )
    parser.add_argument(
        "--pre-roll",
        type=float,
        default=5.0,
        help="Seconds of footage to capture before the peak event."
    )
    parser.add_argument(
        "--post-roll",
        type=float,
        default=5.0,
        help="Seconds of footage to capture after the peak event."
    )
    parser.add_argument(
        "--min-gap",
        type=float,
        default=10.0,
        help="Minimum gap (seconds) between separate highlights to prevent overlap."
    )
    return parser.parse_args()

def translate_to_windows_path(path):
    if path.startswith("/mnt/"):
        parts = path.split("/")
        drive = parts[2].upper()
        return f"{drive}:/" + "/".join(parts[3:])
    
    try:
        res = subprocess.run(["wslpath", "-w", path], capture_output=True, text=True, check=True)
        return res.stdout.strip().replace("\\", "/")
    except Exception:
        return path.replace("\\", "/")

def load_telemetry_data(video_path):
    win_scratch_dir = "C:/Users/me/.gemini/antigravity/scratch"
    camera_json_wsl = "/mnt/c/Users/me/.gemini/antigravity/scratch/camera.json"
    win_camera_json = f"{win_scratch_dir}/camera.json"
    
    # Run Gyroflow.exe to export the metadata
    gyroflow_exe = "/mnt/c/Users/me/.gemini/antigravity/scratch/Gyroflow/Gyroflow.exe"
    
    win_video_path = translate_to_windows_path(video_path)
    
    print(f"[Telemetry] Exporting parsed telemetry (type 2) using Gyroflow CLI...")
    cmd = [
        gyroflow_exe,
        win_video_path,
        "--export-metadata",
        f"2:{win_camera_json}",
        "-f"
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if res.returncode != 0:
        print(f"[Telemetry] Gyroflow CLI failed: {res.stderr.decode()}")
        sys.exit(1)
        
    print(f"[Telemetry] Loading exported camera telemetry: {camera_json_wsl}...")
    with open(camera_json_wsl, 'r') as f:
        data = json.load(f)
        
    return data.get("raw_imu", [])

def analyze_telemetry(raw_imu_list, threshold):
    print(f"[Telemetry] Scanning {len(raw_imu_list)} IMU samples for angular velocity spikes...")
    
    anomalies = [] # list of (video_timestamp, magnitude)
    
    for sample in raw_imu_list:
        ts = sample.get("timestamp_ms", 0.0)
        video_time_sec = ts / 1000.0
        
        # Skip pre-roll samples (negative timestamps)
        if video_time_sec < 0:
            continue
            
        gyro = sample.get("gyro", [0.0, 0.0, 0.0])
        if not isinstance(gyro, list) or len(gyro) < 3:
            continue
            
        # Gyro values in raw_imu exported by Gyroflow are in degrees/second
        gx, gy, gz = gyro[0], gyro[1], gyro[2]
        
        # Convert to rad/s for comparison with threshold
        gx_rad = gx * math.pi / 180.0
        gy_rad = gy * math.pi / 180.0
        gz_rad = gz * math.pi / 180.0
        
        # Calculate magnitude of angular velocity (rad/s)
        magnitude = math.sqrt(gx_rad*gx_rad + gy_rad*gy_rad + gz_rad*gz_rad)
        
        if magnitude >= threshold:
            anomalies.append((video_time_sec, magnitude))
                
    return anomalies

def cluster_highlights(anomalies, pre_roll, post_roll, min_gap):
    if not anomalies:
        return []
        
    # Sort anomalies by timestamp
    anomalies.sort(key=lambda x: x[0])
    
    segments = []
    
    # Initialize first segment
    current_start = max(0.0, anomalies[0][0] - pre_roll)
    current_end = anomalies[0][0] + post_roll
    current_peak_mag = anomalies[0][1]
    current_peak_time = anomalies[0][0]
    
    for time_sec, mag in anomalies[1:]:
        start_candidate = max(0.0, time_sec - pre_roll)
        end_candidate = time_sec + post_roll
        
        # If this event overlaps or is within the min_gap of the current segment
        if start_candidate <= current_end + min_gap:
            # Extend current segment
            current_end = max(current_end, end_candidate)
            if mag > current_peak_mag:
                current_peak_mag = mag
                current_peak_time = time_sec
        else:
            # Save completed segment
            segments.append({
                "start": current_start,
                "end": current_end,
                "peak_time": current_peak_time,
                "peak_mag": current_peak_mag
            })
            # Start new segment
            current_start = start_candidate
            current_end = end_candidate
            current_peak_mag = mag
            current_peak_time = time_sec
            
    # Add final segment
    segments.append({
        "start": current_start,
        "end": current_end,
        "peak_time": current_peak_time,
        "peak_mag": current_peak_mag
    })
    
    return segments

def extract_clips(video_path, segments, output_dir):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    base_name = os.path.splitext(os.path.basename(video_path))[0]
    
    print(f"[FFmpeg] Starting lossless slicing of {len(segments)} highlight clips...")
    
    for idx, seg in enumerate(segments):
        start = seg["start"]
        duration = seg["end"] - start
        
        output_file = os.path.join(
            output_dir, 
            f"{base_name}_highlight_{idx+1:02d}_peak_{seg['peak_time']:.1f}s.mp4"
        )
        
        # Command for lossless stream copy cutting (highly efficient)
        cmd = [
            "ffmpeg", "-y",
            "-ss", f"{start:.3f}",
            "-i", video_path,
            "-t", f"{duration:.3f}",
            "-c", "copy",
            output_file
        ]
        
        print(f"[FFmpeg] Slicing Clip {idx+1} ({start:.1f}s -> {seg['end']:.1f}s, dur: {duration:.1f}s)")
        
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode != 0:
            print(f"[FFmpeg] Error slicing clip {idx+1}: {res.stderr.decode()}")
        else:
            print(f"[FFmpeg] Saved highlight: {output_file}")

def main():
    args = parse_args()
    
    if not os.path.exists(args.video):
        print(f"Error: Video file not found at {args.video}")
        sys.exit(1)
        
    target_file = args.video
    if args.gyroflow and os.path.exists(args.gyroflow):
        target_file = args.gyroflow
        
    raw_imu_list = load_telemetry_data(target_file)
    if not raw_imu_list:
        print("Error: No IMU data parsed from telemetry.")
        sys.exit(1)
        
    anomalies = analyze_telemetry(raw_imu_list, args.threshold)
    print(f"[Telemetry] Detected {len(anomalies)} telemetry anomalies exceeding {args.threshold} rad/s threshold.")
    
    segments = cluster_highlights(anomalies, args.pre_roll, args.post_roll, args.min_gap)
    print(f"[Telemetry] Clustered anomalies into {len(segments)} unique highlight segments.")
    
    if not segments:
        print("[Telemetry] No highlights found. Try reducing the --threshold parameter.")
        sys.exit(0)
        
    extract_clips(args.video, segments, args.output_dir)
    print("[Telemetry] Highlight extraction complete!")

if __name__ == "__main__":
    main()
