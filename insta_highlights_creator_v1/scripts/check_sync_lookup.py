import cv2
import json
import numpy as np

def main():
    video_path = "/mnt/e/202511_Insta360/014/temp_front_30s.mp4"
    camera_json_path = "/mnt/c/Users/me/.gemini/antigravity/scratch/camera.json"
    
    with open(camera_json_path, "r") as f:
        metadata = json.load(f)
        
    meta_ts = np.array([m['timestamp_ms'] for m in metadata])
    
    cap = cv2.VideoCapture(video_path)
    
    print("Matching first 15 frames:")
    for f_idx in range(15):
        # OpenCV gets the timestamp of the NEXT frame to be read
        t_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
        ret, frame = cap.read()
        if not ret:
            break
            
        # Find closest telemetry timestamp
        diffs = np.abs(meta_ts - t_ms)
        closest_idx = np.argmin(diffs)
        closest_ts = meta_ts[closest_idx]
        diff = t_ms - closest_ts
        
        print(f"Frame {f_idx:2d} | OpenCV: {t_ms:8.2f} ms | Closest Telemetry: {closest_ts:8.2f} ms | Diff: {diff:+.2f} ms | Meta Index: {closest_idx}")
        
    cap.release()

if __name__ == "__main__":
    main()
