#!/usr/bin/env python3
import cv2
import json
import numpy as np
import os
import shutil
import subprocess
import sys
import time

def main():
    video_input = "/mnt/e/202511_Insta360/014/VID_20251123_104602_00_014.insv"
    tracking_json = "processScratch/tracking_angles.json"
    
    # We timestamp the output files as requested to prevent overwriting previous versions
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    output_360_8k = f"/mnt/e/202511_Insta360/014/outputHighlights/stitched_360_30s_8k_{timestamp}.mp4"
    output_reframed_4k = f"/mnt/e/202511_Insta360/014/outputHighlights/stitched_stabilized_30s_8k_reframed_tracking_f1160_template_{timestamp}.mp4"

    # 30 seconds at 29.97 fps is ~900 frames (0 to 899)
    num_frames = 900
    frame_indices = "-".join(str(i) for i in range(num_frames))

    # Local temp directory for JPEGs
    temp_frames_dir = "processScratch/frames_template_temp"
    if os.path.exists(temp_frames_dir):
        shutil.rmtree(temp_frames_dir)
    os.makedirs(temp_frames_dir, exist_ok=True)

    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = "/usr/lib/wsl/lib:./thirdParty/insta360Sdk/lib"

    print("\n=========================================")
    print("STEP 1: Stitching 30s 360 Video at 8K with Static Template")
    print("=========================================")

    stitcher_cmd = [
        "./build/stitcher",
        "-inputs", video_input,
        "-image_sequence_dir", temp_frames_dir,
        "-export_frame_index", frame_indices,
        "-output_size", "7680x3840",
        "-stitch_type", "optflow", # Using optical flow as preferred by the user
        "-enable_flowstate",
        "-enable_directionlock",
        "-enable_defringe",
        "-camera_accessory_type", "0",
        "-model_root_dir", "thirdParty/insta360Sdk/models/"
    ]

    print(f"Running stitcher: {' '.join(stitcher_cmd)}")
    res = subprocess.run(stitcher_cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if res.returncode != 0:
        print(f"Stitcher failed: {res.stderr.decode()}")
        if os.path.exists(temp_frames_dir):
            shutil.rmtree(temp_frames_dir)
        sys.exit(1)

    print("\n=========================================")
    print("STEP 2: Compiling 8K JPEGs to 8K H.265 360 Video")
    print("=========================================")

    ffmpeg_8k_cmd = [
        "ffmpeg", "-y",
        "-framerate", "29.97",
        "-i", f"{temp_frames_dir}/%d.jpg",
        "-c:v", "hevc_nvenc",
        "-b:v", "150M",
        "-pix_fmt", "yuv420p",
        output_360_8k
    ]

    print(f"Running 8K encoding: {' '.join(ffmpeg_8k_cmd)}")
    res = subprocess.run(ffmpeg_8k_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if res.returncode != 0:
        print(f"8K FFmpeg encoding failed: {res.stderr.decode()}")
        if os.path.exists(temp_frames_dir):
            shutil.rmtree(temp_frames_dir)
        sys.exit(1)

    # Clean up temp frames
    if os.path.exists(temp_frames_dir):
        shutil.rmtree(temp_frames_dir)

    print("\n=========================================")
    print("STEP 3: Reframing 8K Template Stitched to Final 4K UHD Video")
    print("=========================================")

    # Load smoothed tracking angles (which have Gaussian sigma=50 filter applied!)
    with open(tracking_json, "r") as f:
        tracking_data = json.load(f)

    cap = cv2.VideoCapture(output_360_8k)
    
    # Target output dimensions
    W_out, H_out = 3840, 2160
    
    # Precompute base rays in camera space using Equidistant Fisheye projection
    print("Precomputing camera space rays...")
    u = np.arange(W_out)
    v = np.arange(H_out)
    uu, vv = np.meshgrid(u, v)

    cx = W_out / 2.0
    cy = H_out / 2.0
    
    f_val = 0.53704 * H_out  # f = 1160.0 pixels

    x_cam = (uu - cx) / f_val
    y_cam = (vv - cy) / f_val

    r = np.sqrt(x_cam**2 + y_cam**2)
    theta = np.arctan2(y_cam, x_cam)
    
    r = np.maximum(r, 1e-6)
    phi = r
    
    x_sphere = np.sin(phi) * np.cos(theta)
    y_sphere = np.sin(phi) * np.sin(theta)
    z_sphere = np.cos(phi)

    y_sphere = -y_sphere

    rays = np.stack([x_sphere, y_sphere, z_sphere], axis=-1).reshape(-1, 3)

    # Set up FFmpeg pipe for reframed 4K HEVC encoding
    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-s", f"{W_out}x{H_out}",
        "-pix_fmt", "bgr24",
        "-r", "29.97",
        "-i", "-",
        "-c:v", "hevc_nvenc",
        "-b:v", "100M",
        "-pix_fmt", "yuv420p",
        output_reframed_4k
    ]

    print(f"Launching FFmpeg encoder: {' '.join(ffmpeg_cmd)}")
    proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    start_time = time.time()
    frame_idx = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx >= len(tracking_data):
            break

        H_in, W_in = frame.shape[:2]

        t_info = tracking_data[frame_idx]
        yaw = t_info["yaw_smooth"]
        pitch = t_info["pitch_smooth"]

        # Apply -15.0 degree pitch offset to center the rider + hydrofoil
        y_val = yaw
        p_val = -(pitch - 15.0)

        # Compute rotation matrices
        y_rad = np.radians(y_val)
        p_rad = np.radians(p_val)
        
        cos_y, sin_y = np.cos(y_rad), np.sin(y_rad)
        R_y = np.array([
            [cos_y, 0, sin_y],
            [0, 1, 0],
            [-sin_y, 0, cos_y]
        ])
        
        cos_p, sin_p = np.cos(p_rad), np.sin(p_rad)
        R_x = np.array([
            [1, 0, 0],
            [0, cos_p, -sin_p],
            [0, sin_p, cos_p]
        ])

        R = R_y @ R_x
        rotated_rays = rays @ R.T

        lon = np.arctan2(rotated_rays[:, 0], rotated_rays[:, 2])
        lat = np.arcsin(rotated_rays[:, 1])

        map_x = ((lon + np.pi) / (2.0 * np.pi)) * W_in
        map_y = ((np.pi/2.0 - lat) / np.pi) * H_in

        map_x = map_x.reshape(H_out, W_out).astype(np.float32)
        map_y = map_y.reshape(H_out, W_out).astype(np.float32)

        out_frame = cv2.remap(frame, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP)

        proc.stdin.write(out_frame.tobytes())

        frame_idx += 1
        if frame_idx % 50 == 0:
            elapsed = time.time() - start_time
            fps = frame_idx / elapsed
            print(f"Reframed {frame_idx}/{len(tracking_data)} frames... ({fps:.2f} fps)")

    cap.release()
    
    stdout, stderr = proc.communicate()
    if proc.returncode != 0:
        print(f"FFmpeg failed with exit code {proc.returncode}")
        print(stderr.decode())
        sys.exit(1)

    print("\n=========================================")
    print("Pipeline compilation complete!")
    print(f"1. 8K 360 Video: {output_360_8k}")
    print(f"2. Final 4K Reframed Video: {output_reframed_4k}")
    print("=========================================")

if __name__ == "__main__":
    main()
