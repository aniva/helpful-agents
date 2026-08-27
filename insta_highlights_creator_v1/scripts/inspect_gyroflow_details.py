import json
import os

def main():
    path = "/mnt/e/202511_Insta360/014/VID_20251123_104602_00_014.gyroflow"
    print(f"Loading {path}...")
    with open(path, "r") as f:
        d = json.load(f)
        
    print(f"Top-level keys: {list(d.keys())}")
    
    # Check general settings
    for k in ['gyro_source', 'stabilization', 'meta', 'quats_rotation', 'imu_orientation', 'offsets']:
        if k in d:
            print(f"{k}: {d[k]}")
        else:
            # Check nested keys
            for root_key in d.keys():
                if isinstance(d[root_key], dict) and k in d[root_key]:
                    print(f"d['{root_key}']['{k}']: {d[root_key][k]}")
                    
    # Look at calibration data
    if 'calibration_data' in d:
        cal = d['calibration_data']
        print(f"calibration_data keys: {list(cal.keys())}")
        if 'camera' in cal:
            print(f"camera: {cal['camera']}")

if __name__ == "__main__":
    main()
