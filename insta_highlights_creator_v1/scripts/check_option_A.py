import os
import sys
import cv2
import json
import torch
import numpy as np

sys.path.append("/home/me/repos/helpful-agents/insta_highlights_creator")
from video_processor import FisheyeProjector

class CustomProjector(FisheyeProjector):
    def project_matrix(self, t_front, t_rear, R, overlap_deg=10):
        H_lens, W_lens = t_front.shape[2], t_front.shape[3]
        c_x, c_y = W_lens / 2.0, H_lens / 2.0
        R_max = min(W_lens, H_lens) / 2.0
        alpha_max = np.radians(self.max_lens_fov / 2.0)
        
        if not isinstance(R, torch.Tensor):
            R_t = torch.tensor(R, dtype=torch.float32, device=self.device)
        else:
            R_t = R.to(self.device).float()
            
        vectors_rot = torch.matmul(self.vectors_n_pt, R_t.t())
        
        X_w = vectors_rot[..., 0]
        Y_w = vectors_rot[..., 1]
        Z_w = vectors_rot[..., 2]
        
        alpha_0 = torch.acos(torch.clamp(Z_w, -1.0, 1.0))
        beta_0 = torch.atan2(Y_w, X_w)
        r_norm_0 = alpha_0 / alpha_max
        map_x0 = c_x + R_max * r_norm_0 * torch.cos(beta_0)
        map_y0 = c_y + R_max * r_norm_0 * torch.sin(beta_0)
        
        alpha_1 = torch.acos(torch.clamp(-Z_w, -1.0, 1.0))
        beta_1 = torch.atan2(Y_w, -X_w)
        r_norm_1 = alpha_1 / alpha_max
        map_x1 = c_x + R_max * r_norm_1 * torch.cos(beta_1)
        map_y1 = c_y + R_max * r_norm_1 * torch.sin(beta_1)
        
        grid_x0 = (map_x0 / (W_lens - 1)) * 2.0 - 1.0
        grid_y0 = (map_y0 / (H_lens - 1)) * 2.0 - 1.0
        self.cached_grid_0 = torch.stack([grid_x0, grid_y0], dim=-1).unsqueeze(0)
        
        grid_x1 = (map_x1 / (W_lens - 1)) * 2.0 - 1.0
        grid_y1 = (map_y1 / (H_lens - 1)) * 2.0 - 1.0
        self.cached_grid_1 = torch.stack([grid_x1, grid_y1], dim=-1).unsqueeze(0)
        
        delta = np.radians(overlap_deg)
        eq_max = np.radians(90.0) + delta
        w_front = torch.clamp((eq_max - alpha_0) / (2.0 * delta), 0.0, 1.0)
        self.cached_w_front = w_front.unsqueeze(0).unsqueeze(0)
        
        warp_front = torch.nn.functional.grid_sample(t_front, self.cached_grid_0, mode='bilinear', padding_mode='zeros', align_corners=True)
        warp_rear = torch.nn.functional.grid_sample(t_rear, self.cached_grid_1, mode='bilinear', padding_mode='zeros', align_corners=True)
        blended = warp_front * self.cached_w_front + warp_rear * (1.0 - self.cached_w_front)
        
        output_frame = blended.squeeze(0).permute(1, 2, 0).byte().contiguous().cpu().numpy()
        return output_frame

def quat_to_matrix(q):
    w, x, y, z = q
    norm = np.sqrt(w*w + x*x + y*y + z*z)
    w /= norm
    x /= norm
    y /= norm
    z /= norm
    return np.array([
        [1 - 2*y**2 - 2*z**2, 2*x*y - 2*w*z, 2*x*z + 2*w*y],
        [2*x*y + 2*w*z, 1 - 2*x**2 - 2*z**2, 2*y*z - 2*w*x],
        [2*x*z - 2*w*y, 2*y*z + 2*w*x, 1 - 2*x**2 - 2*y**2]
    ], dtype=np.float32)

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
    video_front = "/mnt/e/202511_Insta360/014/temp_front_30s.mp4"
    video_rear = "/mnt/e/202511_Insta360/014/temp_rear_30s.mp4"
    camera_json_path = "/mnt/c/Users/me/.gemini/antigravity/scratch/camera.json"
    
    with open(camera_json_path, "r") as f:
        metadata = json.load(f)
        
    cap_f = cv2.VideoCapture(video_front)
    cap_r = cv2.VideoCapture(video_rear)
    
    projector = CustomProjector(640, 360, fov_deg=95)
    
    # We test Option A: r.T @ s
    perm = (0, 2, 1)
    signs = (1, -1, 1)
    P = np.zeros((3, 3), dtype=np.float32)
    for i in range(3):
        P[i, perm[i]] = signs[i]
        
    # We also sweep a constant roll offset to see if we can find a flat horizon
    theta = np.radians(40.0) # we start with 40 degrees based on mean value in sweep
    R_roll = np.array([
        [np.cos(theta), -np.sin(theta), 0],
        [np.sin(theta), np.cos(theta), 0],
        [0, 0, 1]
    ], dtype=np.float32)
    
    rolls = []
    
    for f_idx in range(300):
        ret_f, frame_f = cap_f.read()
        ret_r, frame_r = cap_r.read()
        if not ret_f or not ret_r:
            break
            
        m = metadata[f_idx]
        org_quat = m['org_quat']
        stab_quat = m['stab_quat']
        
        R_raw = quat_to_matrix(org_quat)
        R_stab = quat_to_matrix(stab_quat)
        
        R_raw_proj = P @ R_raw @ P.T
        R_stab_proj = P @ R_stab @ P.T
        
        R = R_raw_proj.T @ R_stab_proj @ R_roll
        
        out_frame = projector.project(frame_f, frame_r, R=R)
        
        # Save frame 10 for visual inspection
        if f_idx == 10:
            cv2.imwrite("/mnt/c/Users/me/.gemini/antigravity/brain/64681769-3704-4a64-a001-c7bedf088c94/scratch/horizon_A_test.png", out_frame)
            
        roll = estimate_roll(out_frame)
        if roll is not None:
            rolls.append(roll)
            
    cap_f.release()
    cap_r.release()
    
    if len(rolls) > 50:
        rolls = np.array(rolls)
        print(f"Total evaluated: {len(rolls)}/300")
        print(f"Mean roll: {np.mean(rolls):.2f} degrees")
        print(f"Std roll (wobble): {np.std(rolls):.2f} degrees")
    else:
        print("Not enough frames with detected horizon.")

if __name__ == "__main__":
    main()
