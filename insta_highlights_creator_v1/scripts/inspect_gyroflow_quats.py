import json
import os

def main():
    path = "/mnt/e/202511_Insta360/014/VID_20251123_104602_00_014.gyroflow"
    print(f"Loading {path}...")
    with open(path, "r") as f:
        d = json.load(f)
        
    gs = d.get('gyro_source', {})
    print("Gyro source keys:")
    print(list(gs.keys()))
    
    for key in ['synced_imu_timestamps', 'integrated_quaternions', 'smoothed_quaternions']:
        val = gs.get(key)
        if val is not None:
            print(f"\nKey '{key}' type={type(val)}: length={len(val)}")
            if len(val) > 0:
                print(f"  First 5 elements:")
                for i in range(min(5, len(val))):
                    print(f"    {i}: {val[i]}")
                    
if __name__ == "__main__":
    main()
