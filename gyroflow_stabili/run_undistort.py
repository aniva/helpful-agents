import os
import subprocess
import json
import shutil

def main():
    # Local paths (from WSL perspective)
    local_scratch_dir = "/mnt/c/Users/me/.gemini/antigravity/scratch"
    local_gyroflow_exe = os.path.join(local_scratch_dir, "Gyroflow/Gyroflow.exe")
    local_lens_profile = os.path.join(local_scratch_dir, "Insta360_X5_lens_profile.json")
    local_preset_path = os.path.join(local_scratch_dir, "undistort_preset.json")
    local_front_in = os.path.join(local_scratch_dir, "front_5s.mp4")
    local_rear_in = os.path.join(local_scratch_dir, "rear_5s.mp4")
    local_front_out_expected = os.path.join(local_scratch_dir, "front_5s_undistorted.mp4")
    local_rear_out_expected = os.path.join(local_scratch_dir, "rear_5s_undistorted.mp4")
    local_dest_dir = "/mnt/e/202511_Insta360/014"
    local_dest_front = os.path.join(local_dest_dir, "undistort_front_VID_20251123_104602_00_014_001.mp4")
    local_dest_rear = os.path.join(local_dest_dir, "undistort_rear_VID_20251123_104602_00_014_001.mp4")

    # Windows paths (from Gyroflow perspective)
    win_scratch_dir = r"C:\Users\me\.gemini\antigravity\scratch"
    win_lens_profile = os.path.join(win_scratch_dir, "Insta360_X5_lens_profile.json")
    win_preset_path = os.path.join(win_scratch_dir, "undistort_preset.json")
    win_front_in = os.path.join(win_scratch_dir, "front_5s.mp4")
    win_rear_in = os.path.join(win_scratch_dir, "rear_5s.mp4")

    # 1. Write the Gyroflow preset JSON using local path
    preset_data = {
        "version": 2,
        "stabilization": {
            "fov": 1.0,
            "smoothness": 0.0,
            "horizon_lock": False,
            "dynamic_zoom": False
        }
    }
    with open(local_preset_path, "w") as f:
        json.dump(preset_data, f, indent=2)
    print(f"Created Gyroflow preset: {local_preset_path}")

    # 2. Run Gyroflow on the front stream
    print("\n--- Undistorting FRONT stream ---")
    cmd_front = [
        local_gyroflow_exe,
        win_front_in,
        win_lens_profile,
        "--preset", win_preset_path,
        "-t", "_undistorted",
        "-f",
        "--stdout-progress"
    ]
    print("Running command:", " ".join(cmd_front))
    res_front = subprocess.run(cmd_front, capture_output=True, text=True)
    print("Stdout:", res_front.stdout)
    print("Stderr:", res_front.stderr)

    # 3. Run Gyroflow on the rear stream
    print("\n--- Undistorting REAR stream ---")
    cmd_rear = [
        local_gyroflow_exe,
        win_rear_in,
        win_lens_profile,
        "--preset", win_preset_path,
        "-t", "_undistorted",
        "-f",
        "--stdout-progress"
    ]
    print("Running command:", " ".join(cmd_rear))
    res_rear = subprocess.run(cmd_rear, capture_output=True, text=True)
    print("Stdout:", res_rear.stdout)
    print("Stderr:", res_rear.stderr)

    # 4. Check if output files exist and copy/move them
    print("\n--- Copying output files to destination ---")
    os.makedirs(local_dest_dir, exist_ok=True)
    
    if os.path.exists(local_front_out_expected):
        print(f"Found front output: {local_front_out_expected}. Copying to {local_dest_front}...")
        shutil.copy2(local_front_out_expected, local_dest_front)
    else:
        print(f"Error: Expected front output file {local_front_out_expected} was not created.")
        
    if os.path.exists(local_rear_out_expected):
        print(f"Found rear output: {local_rear_out_expected}. Copying to {local_dest_rear}...")
        shutil.copy2(local_rear_out_expected, local_dest_rear)
    else:
        print(f"Error: Expected rear output file {local_rear_out_expected} was not created.")
        
    print("\nProcess finished.")

if __name__ == "__main__":
    main()
