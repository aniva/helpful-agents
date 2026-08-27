import json
import numpy as np

def main():
    camera_json_path = "/mnt/c/Users/me/.gemini/antigravity/scratch/camera.json"
    with open(camera_json_path, "r") as f:
        metadata = json.load(f)
        
    print(f"Total metadata frames: {len(metadata)}")
    
    # Check the first 40 frames
    eulers = np.array([m['org_euler'] for m in metadata[:40]])
    
    print("\nFirst 40 frames motion range:")
    for i, name in enumerate(['Roll', 'Pitch', 'Yaw']):
        vals = eulers[:, i]
        print(f"{name:<5} | Min: {np.min(vals):.2f} deg | Max: {np.max(vals):.2f} deg | Std: {np.std(vals):.2f} deg")
        
    # Check the full video
    eulers_all = np.array([m['org_euler'] for m in metadata])
    print("\nFull video motion range:")
    for i, name in enumerate(['Roll', 'Pitch', 'Yaw']):
        vals = eulers_all[:, i]
        print(f"{name:<5} | Min: {np.min(vals):.2f} deg | Max: {np.max(vals):.2f} deg | Std: {np.std(vals):.2f} deg")

if __name__ == "__main__":
    main()
