import json
import os

def main():
    path = "/mnt/e/202511_Insta360/014/VID_20251123_104602_00_014.gyroflow"
    print(f"Loading {path}...")
    with open(path, "r") as f:
        d = json.load(f)
        
    print("Top-level keys in .gyroflow project JSON:")
    print(list(d.keys()))
    
    # Check for offsets, lens profiles, or stabilized data
    for k in ['gyroflow_version', 'camera_name', 'lens_model', 'sync_points', 'offsets', 'gyro_data']:
        if k in d:
            val = d[k]
            if isinstance(val, (dict, list)):
                print(f"\nKey '{k}' type={type(val)}: length={len(val)}")
                if isinstance(val, dict):
                    print(f"  keys={list(val.keys())}")
            else:
                print(f"\nKey '{k}' value={val}")
                
if __name__ == "__main__":
    main()
