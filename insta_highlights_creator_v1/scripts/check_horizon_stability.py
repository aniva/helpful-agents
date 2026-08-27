import cv2
import numpy as np

def estimate_roll(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)
    lines = cv2.HoughLines(edges, 1, np.pi / 180, 60)
    if lines is not None:
        for rho, theta in lines[:, 0]:
            angle_deg = np.degrees(theta)
            if angle_deg > 90:
                angle_deg -= 180
            return angle_deg
    return None

def main():
    video_path = "/mnt/e/202511_Insta360/014/test_gyroflow_quat_stab.mp4"
    cap = cv2.VideoCapture(video_path)
    
    rolls = []
    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        roll = estimate_roll(frame)
        if roll is not None:
            rolls.append(roll)
        frame_idx += 1
        
    cap.release()
    
    if len(rolls) > 0:
        rolls = np.array(rolls)
        print(f"Total frames evaluated: {len(rolls)}/{frame_idx}")
        print(f"Mean roll: {np.mean(rolls):.2f} degrees")
        print(f"Std roll (horizon wobble): {np.std(rolls):.2f} degrees")
        print(f"Min roll: {np.min(rolls):.2f} degrees, Max roll: {np.max(rolls):.2f} degrees")
    else:
        print("No horizon detected in any frame.")

if __name__ == "__main__":
    main()
