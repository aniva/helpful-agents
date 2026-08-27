import json
import os

def main():
    path = "/mnt/e/202511_Insta360/014/VID_20251123_104602_00_014.gyroflow"
    print(f"Loading {path}...")
    with open(path, "r") as f:
        d = json.load(f)
        
    for k in ['calibration_data', 'gyro_source', 'stabilization', 'synchronization']:
        if k in d:
            val = d[k]
            print(f"\n================ {k} ================")
            print(f"Type: {type(val)}")
            if isinstance(val, dict):
                print(f"Keys: {list(val.keys())}")
                # Print subset of keys or sizes
                for sk, sv in val.items():
                    if isinstance(sv, (dict, list)):
                        print(f"  Subkey '{sk}': type={type(sv)}, length={len(sv)}")
                        if sk == 'quaternions' and len(sv) > 0:
                            print(f"    First quaternion: {sv[0]}")
                        if sk == 'gyroscope' and len(sv) > 0:
                            print(f"    First gyro: {sv[0]}")
                    else:
                        print(f"  Subkey '{sk}': value={sv}")
            else:
                print(f"Value: {val}")
                
if __name__ == "__main__":
    main()
