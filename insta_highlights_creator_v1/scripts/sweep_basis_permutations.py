import os
import sys
import cv2
import json
import torch
import numpy as np
import itertools

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
        
        # Front lens mapping (+Z)
        alpha_0 = torch.acos(torch.clamp(Z_w, -1.0, 1.0))
        beta_0 = torch.atan2(Y_w, X_w)
        r_norm_0 = alpha_0 / alpha_max
        map_x0 = c_x + R_max * r_norm_0 * torch.cos(beta_0)
        map_y0 = c_y + R_max * r_norm_0 * torch.sin(beta_0)
        
        # Rear lens mapping (-Z)
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
    
    # Load 200 frames into GPU memory for fast evaluation
    gpu_frames = []
    for _ in range(200):
        ret_f, frame_f = cap_f.read()
        ret_r, frame_r = cap_r.read()
        if not ret_f or not ret_r:
            break
        f_small = cv2.resize(frame_f, (640, 640))
        r_small = cv2.resize(frame_r, (640, 640))
        t_front = torch.from_numpy(f_small).permute(2, 0, 1).unsqueeze(0).float().to("cuda")
        t_rear = torch.from_numpy(r_small).permute(2, 0, 1).unsqueeze(0).float().to("cuda")
        gpu_frames.append((t_front, t_rear))
        
    cap_f.release()
    cap_r.release()
    
    print(f"Loaded {len(gpu_frames)} frames on GPU.")
    
    projector = CustomProjector(640, 360, fov_deg=95)
    
    perms = list(itertools.permutations([0, 1, 2]))
    signs = list(itertools.product([1, -1], repeat=3))
    
    results = []
    
    for perm in perms:
        for sign in signs:
            P = np.zeros((3, 3), dtype=np.float32)
            for i in range(3):
                P[i, perm[i]] = sign[i]
                
            for opt_name, get_R in [
                ("A", lambda r, s: r.T @ s),
                ("B", lambda r, s: r @ s.T),
                ("C", lambda r, s: s.T @ r),
                ("D", lambda r, s: s @ r.T)
            ]:
                rolls = []
                for f_idx, (t_front, t_rear) in enumerate(gpu_frames):
                    m = metadata[f_idx]
                    org_quat = m['org_quat']
                    stab_quat = m['stab_quat']
                    
                    R_raw = quat_to_matrix(org_quat)
                    R_stab = quat_to_matrix(stab_quat)
                    
                    R_raw_proj = P @ R_raw @ P.T
                    R_stab_proj = P @ R_stab @ P.T
                    
                    R = get_R(R_raw_proj, R_stab_proj)
                    
                    out_frame = projector.project_matrix(t_front, t_rear, R)
                    roll = estimate_roll(out_frame)
                    if roll is not None:
                        rolls.append(roll)
                        
                # Require at least 100 detected horizons over 200 frames to be valid
                if len(rolls) > 100:
                    std_val = np.std(rolls)
                    results.append((std_val, perm, sign, opt_name, np.mean(rolls)))
                    
    results.sort(key=lambda x: x[0])
    
    print("\nTop 10 Best Permutations (Over 200 frames):")
    for std_val, perm, sign, opt_name, mean_val in results[:10]:
        print(f"Std: {std_val:.4f} deg | Mean: {mean_val:.2f} deg | Opt: {opt_name} | Perm: {perm} | Signs: {sign}")

if __name__ == "__main__":
    main()
