import os
import sys
import cv2
import json
import torch
import numpy as np
import subprocess

sys.path.append("/home/me/repos/helpful-agents/insta_highlights_creator")
from video_processor import FisheyeProjector

class CustomProjector(FisheyeProjector):
    def project_matrix(self, frame_front, frame_rear, R, overlap_deg=10):
        H_lens, W_lens, _ = frame_front.shape
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
        
        t_front = torch.from_numpy(frame_front).permute(2, 0, 1).unsqueeze(0).float().to(self.device)
        t_rear = torch.from_numpy(frame_rear).permute(2, 0, 1).unsqueeze(0).float().to(self.device)
        
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

def get_pitch_matrix(pitch_deg):
    p = np.radians(pitch_deg)
    cp, sp = np.cos(p), np.sin(p)
    return np.array([
        [1, 0, 0],
        [0, cp, -sp],
        [0, sp, cp]
    ], dtype=np.float32)

def main():
    video_front = "/mnt/e/202511_Insta360/014/temp_front_30s.mp4"
    video_rear = "/mnt/e/202511_Insta360/014/temp_rear_30s.mp4"
    output_path = "/mnt/e/202511_Insta360/014/test_gyroflow_quat_stab.mp4"
    camera_json_path = "/mnt/c/Users/me/.gemini/antigravity/scratch/camera.json"
    
    print("Loading camera metadata...")
    with open(camera_json_path, "r") as f:
        metadata = json.load(f)
        
    print("Opening video captures...")
    cap_f = cv2.VideoCapture(video_front)
    cap_r = cv2.VideoCapture(video_rear)
    fps = cap_f.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        fps = 29.97
        
    W_out, H_out = 1920, 1080
    
    cmd_ffmpeg = [
        'ffmpeg', '-y',
        '-f', 'rawvideo',
        '-vcodec', 'rawvideo',
        '-pix_fmt', 'bgr24',
        '-s', f"{W_out}x{H_out}",
        '-r', f"{fps:.2f}",
        '-i', '-',
        '-c:v', 'h264_nvenc',
        '-preset', 'p1',
        '-cq', '19',
        '-pix_fmt', 'yuv420p',
        output_path
    ]
    proc = subprocess.Popen(cmd_ffmpeg, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    projector = CustomProjector(W_out, H_out, fov_deg=95)
    
    frames_to_render = min(150, len(metadata)) # 5 seconds
    
    print(f"Rendering {frames_to_render} stabilized frames with basis change...")
    
    # Basis permutation matrix for Perm: (0, 2, 1) | Signs: (1, -1, -1)
    # which maps: X_proj = X_gyro, Y_proj = -Z_gyro, Z_proj = -Y_gyro
    P = np.array([
        [1, 0, 0],
        [0, 0, -1],
        [0, -1, 0]
    ], dtype=np.float32)
    
    # 12 degrees constant roll offset
    theta = np.radians(-12.0)
    R_roll = np.array([
        [np.cos(theta), -np.sin(theta), 0],
        [np.sin(theta), np.cos(theta), 0],
        [0, 0, 1]
    ], dtype=np.float32)
    
    # Look pitch of -35 degrees (to see rider)
    R_look = get_pitch_matrix(-35)
    
    for f_idx in range(frames_to_render):
        ret_f, frame_f = cap_f.read()
        ret_r, frame_r = cap_r.read()
        if not ret_f or not ret_r:
            break
            
        m = metadata[f_idx]
        org_quat = m['org_quat']
        stab_quat = m['stab_quat']
        
        # Convert quaternions to rotation matrices
        R_raw = quat_to_matrix(org_quat)
        R_stab = quat_to_matrix(stab_quat)
        
        # Change basis
        R_raw_proj = P @ R_raw @ P.T
        R_stab_proj = P @ R_stab @ P.T
        
        # Stabilize: R = R_raw_proj @ R_stab_proj.T @ R_roll @ R_look
        R = R_raw_proj @ R_stab_proj.T @ R_roll @ R_look
        
        output_frame = projector.project_matrix(frame_f, frame_r, R)
        
        # Draw frame number
        cv2.putText(output_frame, f"Frame {f_idx}", (50, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 255), 3, cv2.LINE_AA)
        
        proc.stdin.write(output_frame.tobytes())
        
    proc.communicate()
    cap_f.release()
    cap_r.release()
    
    print(f"\nStabilized basis-corrected 5-second sample generated at: {output_path}")

if __name__ == "__main__":
    main()
