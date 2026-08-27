#!/usr/bin/env python3
import os
import shutil
import subprocess
import sys

def main():
    video_input = "/mnt/e/202511_Insta360/014/VID_20251123_104602_00_014.insv"
    if not os.path.exists(video_input):
        print(f"Error: Input video not found at {video_input}")
        sys.exit(1)

    # 15 seconds at 29.97 fps is ~450 frames
    num_frames = 450
    frame_indices = "-".join(str(i) for i in range(num_frames))

    # Define combinations
    combos = [
        {"name": "template_unstabilized", "args": ["-stitch_type", "template"]},
        {"name": "template_flowstate", "args": ["-stitch_type", "template", "-enable_flowstate"]},
        {"name": "template_flowstate_dirlock", "args": ["-stitch_type", "template", "-enable_flowstate", "-enable_directionlock"]},
        {"name": "optflow_unstabilized", "args": ["-stitch_type", "optflow"]},
        {"name": "optflow_flowstate", "args": ["-stitch_type", "optflow", "-enable_flowstate"]},
        {"name": "optflow_flowstate_dirlock", "args": ["-stitch_type", "optflow", "-enable_flowstate", "-enable_directionlock"]},
        {"name": "dynamicstitch_unstabilized", "args": ["-stitch_type", "dynamicstitch"]},
        {"name": "dynamicstitch_flowstate", "args": ["-stitch_type", "dynamicstitch", "-enable_flowstate"]},
        {"name": "dynamicstitch_flowstate_dirlock", "args": ["-stitch_type", "dynamicstitch", "-enable_flowstate", "-enable_directionlock"]},
    ]

    # Ensure outputHighlights directory exists
    os.makedirs("outputHighlights", exist_ok=True)

    # Use /dev/shm (RAM disk) for zero-latency frame writing
    temp_frames_dir = "/dev/shm/frames_temp"

    # Set up runtime environment
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = "/usr/lib/wsl/lib:./thirdParty/insta360Sdk/lib"

    for idx, combo in enumerate(combos):
        print(f"\n=========================================")
        print(f"[{idx+1}/{len(combos)}] Running Comparison Combo: {combo['name']}")
        print(f"=========================================")

        # Clean / create temp directory in RAM disk
        if os.path.exists(temp_frames_dir):
            shutil.rmtree(temp_frames_dir)
        os.makedirs(temp_frames_dir, exist_ok=True)

        # 1. Stitch frames using SDK with CUDA (by not passing -disable_cuda)
        # We output at 960x480 resolution for faster frame rendering while maintaining comparison fidelity
        stitcher_cmd = [
            "./build/stitcher",
            "-inputs", video_input,
            "-image_sequence_dir", temp_frames_dir,
            "-export_frame_index", frame_indices,
            "-output_size", "960x480",
            "-camera_accessory_type", "0", # No accessory whatsoever
            "-model_root_dir", "thirdParty/insta360Sdk/models/"
        ] + combo["args"]

        print(f"Running stitcher: {' '.join(stitcher_cmd)}")
        res = subprocess.run(stitcher_cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode != 0:
            print(f"Stitcher failed for combo {combo['name']}: {res.stderr.decode()}")
            continue

        # 2. Encode image sequence to 15s MP4 using FFmpeg (with NVENC hardware acceleration)
        output_mp4 = f"outputHighlights/comparison_{combo['name']}.mp4"
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-framerate", "29.97",
            "-i", f"{temp_frames_dir}/%d.jpg",
            "-c:v", "h264_nvenc",
            "-pix_fmt", "yuv420p",
            output_mp4
        ]

        print(f"Encoding output: {' '.join(ffmpeg_cmd)}")
        res = subprocess.run(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode != 0:
            # Fallback to soft encoder libx264 if nvenc fails
            print(f"NVENC failed, falling back to libx264...")
            ffmpeg_cmd[5] = "libx264"
            res = subprocess.run(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if res.returncode != 0:
                print(f"FFmpeg encoding failed: {res.stderr.decode()}")
                continue

        print(f"Successfully generated comparison clip: {output_mp4}")

    # Clean up temp frames in RAM disk
    if os.path.exists(temp_frames_dir):
        shutil.rmtree(temp_frames_dir)

    print("\n=========================================")
    print("All SDK option comparisons generated in outputHighlights/!")
    print("=========================================")

if __name__ == "__main__":
    main()
