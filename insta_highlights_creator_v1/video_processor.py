import os
import glob
import re
import time
import subprocess
import json
import numpy as np
import cv2
import torch
import gc
from ultralytics import YOLO

class FisheyeProjector:
    def __init__(self, W_out, H_out, fov_deg=90, max_lens_fov_deg=200, force_cpu=False):
        self.W_out = W_out
        self.H_out = H_out
        self.fov_deg = fov_deg
        self.max_lens_fov = max_lens_fov_deg
        
        # Check CUDA availability
        self.use_cuda = torch.cuda.is_available() and not force_cpu
        self.device = torch.device("cuda" if self.use_cuda else "cpu")
        
        # Precompute the camera space grid
        self.vectors_n_np = self._precompute_grid()
        if self.use_cuda:
            self.vectors_n_pt = torch.from_numpy(self.vectors_n_np).to(self.device).float()
            
        # Cache for projection grids to prevent VRAM allocation bloat
        self.last_angles = None
        self.cached_grid_0 = None
        self.cached_grid_1 = None
        self.cached_w_front = None
        
    def _precompute_grid(self):
        fov_rad = np.radians(self.fov_deg)
        f_cam = 1.0 / np.tan(fov_rad / 2.0)
        
        u = np.arange(self.W_out)
        v = np.arange(self.H_out)
        u_grid, v_grid = np.meshgrid(u, v)
        
        # Normalize coordinates relative to camera center
        # x: right, y: down, z: forward
        x = (u_grid - self.W_out / 2.0) / (self.W_out / 2.0)
        y = (v_grid - self.H_out / 2.0) / (self.W_out / 2.0)
        z = np.full_like(x, f_cam)
        
        vectors = np.stack([x, y, z], axis=-1)
        norms = np.linalg.norm(vectors, axis=-1, keepdims=True)
        return (vectors / norms).astype(np.float32)

    def get_rotation_matrix(self, yaw, pitch, roll):
        cy, sy = np.cos(yaw), np.sin(yaw)
        cp, sp = np.cos(pitch), np.sin(pitch)
        cr, sr = np.cos(roll), np.sin(roll)
        
        R_yaw = np.array([
            [cy, 0, sy],
            [0, 1, 0],
            [-sy, 0, cy]
        ])
        R_pitch = np.array([
            [1, 0, 0],
            [0, cp, -sp],
            [0, sp, cp]
        ])
        R_roll = np.array([
            [cr, -sr, 0],
            [sr, cr, 0],
            [0, 0, 1]
        ])
        return (R_yaw @ R_pitch @ R_roll).astype(np.float32)

    def project(self, frame_front, frame_rear, yaw=0.0, pitch=0.0, roll=0.0, R=None, overlap_deg=10):
        if self.use_cuda:
            return self.project_cuda(frame_front, frame_rear, yaw, pitch, roll, R, overlap_deg)
        else:
            return self.project_cpu(frame_front, frame_rear, yaw, pitch, roll, R, overlap_deg)

    def project_cpu(self, frame_front, frame_rear, yaw=0.0, pitch=0.0, roll=0.0, R=None, overlap_deg=10):
        """
        Projects front and rear circular fisheye frames into a single perspective frame on CPU.
        """
        H_lens, W_lens, _ = frame_front.shape
        c_x, c_y = W_lens / 2.0, H_lens / 2.0
        R_max = min(W_lens, H_lens) / 2.0
        alpha_max = np.radians(self.max_lens_fov / 2.0)
        
        # Check cache (on CPU)
        if R is not None:
            R_comp = tuple(np.array(R).flatten().tolist())
            angles = (R_comp, H_lens, W_lens, overlap_deg)
        else:
            angles = (yaw, pitch, roll, H_lens, W_lens, overlap_deg)
            
        if self.last_angles != angles:
            # Rotate coordinates
            if R is None:
                R_cpu = self.get_rotation_matrix(yaw, pitch, roll)
            else:
                R_cpu = np.array(R, dtype=np.float32)
            vectors_rot = np.dot(self.vectors_n_np, R_cpu.T)
            
            X_w = vectors_rot[..., 0]
            Y_w = vectors_rot[..., 1]
            Z_w = vectors_rot[..., 2]
            
            # Front lens mapping (+Z)
            alpha_0 = np.arccos(np.clip(Z_w, -1.0, 1.0))
            beta_0 = np.arctan2(Y_w, X_w)
            r_norm_0 = alpha_0 / alpha_max
            self.cached_grid_0 = (
                (c_x + R_max * r_norm_0 * np.cos(beta_0)).astype(np.float32),
                (c_y + R_max * r_norm_0 * np.sin(beta_0)).astype(np.float32)
            )
            
            # Rear lens mapping (-Z)
            alpha_1 = np.arccos(np.clip(-Z_w, -1.0, 1.0))
            beta_1 = np.arctan2(Y_w, -X_w)
            r_norm_1 = alpha_1 / alpha_max
            self.cached_grid_1 = (
                (c_x + R_max * r_norm_1 * np.cos(beta_1)).astype(np.float32),
                (c_y + R_max * r_norm_1 * np.sin(beta_1)).astype(np.float32)
            )
            
            # Blending mask
            delta = np.radians(overlap_deg)
            eq_max = np.radians(90.0) + delta
            w_front = np.clip((eq_max - alpha_0) / (2.0 * delta), 0.0, 1.0)
            self.cached_w_front = np.expand_dims(w_front, axis=-1).astype(np.float32)
            
            self.last_angles = angles
            
        # Remap both hemispheres using cached coordinates
        warp_front = cv2.remap(frame_front, self.cached_grid_0[0], self.cached_grid_0[1], cv2.INTER_LINEAR)
        warp_rear = cv2.remap(frame_rear, self.cached_grid_1[0], self.cached_grid_1[1], cv2.INTER_LINEAR)
        
        # Combine
        blended = warp_front * self.cached_w_front + warp_rear * (1.0 - self.cached_w_front)
        return blended.astype(np.uint8)

    def project_cuda(self, frame_front, frame_rear, yaw=0.0, pitch=0.0, roll=0.0, R=None, overlap_deg=10):
        """
        Projects front and rear circular fisheye frames into a single perspective frame on GPU.
        """
        H_lens, W_lens, _ = frame_front.shape
        
        # Check cache (on GPU)
        if R is not None:
            if isinstance(R, torch.Tensor):
                R_comp = tuple(R.flatten().tolist())
            else:
                R_comp = tuple(np.array(R).flatten().tolist())
            angles = (R_comp, H_lens, W_lens, overlap_deg)
        else:
            angles = (yaw, pitch, roll, H_lens, W_lens, overlap_deg)
            
        if self.last_angles != angles:
            c_x, c_y = W_lens / 2.0, H_lens / 2.0
            R_max = min(W_lens, H_lens) / 2.0
            alpha_max = np.radians(self.max_lens_fov / 2.0)
            
            if R is None:
                # Create rotation matrices on GPU
                cy, sy = np.cos(yaw), np.sin(yaw)
                cp, sp = np.cos(pitch), np.sin(pitch)
                cr, sr = np.cos(roll), np.sin(roll)
                
                R_yaw = torch.tensor([
                    [cy, 0, sy],
                    [0, 1, 0],
                    [-sy, 0, cy]
                ], dtype=torch.float32, device=self.device)
                R_pitch = torch.tensor([
                    [1, 0, 0],
                    [0, cp, -sp],
                    [0, sp, cp]
                ], dtype=torch.float32, device=self.device)
                R_roll = torch.tensor([
                    [cr, -sr, 0],
                    [sr, cr, 0],
                    [0, 0, 1]
                ], dtype=torch.float32, device=self.device)
                
                R_gpu = R_yaw @ R_pitch @ R_roll
            else:
                if not isinstance(R, torch.Tensor):
                    R_gpu = torch.tensor(R, dtype=torch.float32, device=self.device)
                else:
                    R_gpu = R.to(self.device).float()
            
            # Rotate precomputed vectors: shape (H_out, W_out, 3)
            vectors_rot = torch.matmul(self.vectors_n_pt, R_gpu.t())
            
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
            
            # Normalize maps to [-1, 1] for grid_sample
            grid_x0 = (map_x0 / (W_lens - 1)) * 2.0 - 1.0
            grid_y0 = (map_y0 / (H_lens - 1)) * 2.0 - 1.0
            self.cached_grid_0 = torch.stack([grid_x0, grid_y0], dim=-1).unsqueeze(0) # (1, H_out, W_out, 2)
            
            grid_x1 = (map_x1 / (W_lens - 1)) * 2.0 - 1.0
            grid_y1 = (map_y1 / (H_lens - 1)) * 2.0 - 1.0
            self.cached_grid_1 = torch.stack([grid_x1, grid_y1], dim=-1).unsqueeze(0) # (1, H_out, W_out, 2)
            
            # Blending mask
            delta = np.radians(overlap_deg)
            eq_max = np.radians(90.0) + delta
            w_front = torch.clamp((eq_max - alpha_0) / (2.0 * delta), 0.0, 1.0)
            self.cached_w_front = w_front.unsqueeze(0).unsqueeze(0) # (1, 1, H_out, W_out)
            
            self.last_angles = angles
            
        # Upload frames to GPU: BGR uint8 -> Float
        t_front = torch.from_numpy(frame_front).permute(2, 0, 1).unsqueeze(0).float().to(self.device)
        t_rear = torch.from_numpy(frame_rear).permute(2, 0, 1).unsqueeze(0).float().to(self.device)
        
        # Run grid_sample
        warp_front = torch.nn.functional.grid_sample(t_front, self.cached_grid_0, mode='bilinear', padding_mode='zeros', align_corners=True)
        warp_rear = torch.nn.functional.grid_sample(t_rear, self.cached_grid_1, mode='bilinear', padding_mode='zeros', align_corners=True)
        
        # Combine
        blended = warp_front * self.cached_w_front + warp_rear * (1.0 - self.cached_w_front)
        
        # Download and convert back to numpy BGR uint8 (make memory layout contiguous for OpenCV compatibility)
        output_frame = blended.squeeze(0).permute(1, 2, 0).byte().contiguous().cpu().numpy()
        return output_frame


class HorizonStabilizer:
    @staticmethod
    def estimate_roll(frame_front, frame_rear):
        """
        Estimates the camera's roll angle by finding the horizon (sky-water line) in the frames.
        """
        # Downsample for speed
        img = cv2.resize(frame_front, (320, 320))
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Blur and edge detection
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 50, 150)
        
        # Hough Lines
        lines = cv2.HoughLines(edges, 1, np.pi / 180, 60)
        
        if lines is not None:
            # Find the most horizontal-like line
            for rho, theta in lines[:, 0]:
                angle_deg = np.degrees(theta)
                # Normalize to [-90, 90]
                if angle_deg > 90:
                    angle_deg -= 180
                # Return the roll angle in radians (offset from horizontal)
                return np.radians(-angle_deg)
                
        # Default to 0 if no clear horizon line is found
        return 0.0


class HighlightAnalyzer:
    def __init__(self, model_size="n"):
        self.device = "cpu"
        # Load CPU-only YOLO model for stable and fast scanning
        self.model = YOLO(f"yolov8{model_size}.pt").to(self.device)
        
    def analyze_video(self, video_path_front, video_path_rear, progress_callback=None):
        """
        Scans the video files frame-by-frame, using 1-FPS YOLOv8 keyframes and 30-Hz MIL tracking
        to calculate absolute 3D target angles for every frame in the video.
        """
        cap_f = cv2.VideoCapture(video_path_front)
        cap_r = cv2.VideoCapture(video_path_rear)
        
        fps = cap_f.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap_f.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps
        
        # Scan settings
        step_frames = int(fps)
        timeline = []
        
        # We project quick perspective views to run object detection (forced to CPU for tracking)
        proj_rider = FisheyeProjector(640, 640, fov_deg=100, force_cpu=True)
        proj_kite = FisheyeProjector(640, 640, fov_deg=100, force_cpu=True)
        fov_rad = np.radians(100)
        
        # Trackers
        tracker_rider = None
        tracker_kite = None
        
        # Keep track of last known coordinates for fallback
        last_rider_yaw, last_rider_pitch = 0.0, np.radians(-35)
        last_kite_yaw, last_kite_pitch = np.radians(180), np.radians(35)
        
        frame_idx = 0
        while cap_f.isOpened() and cap_r.isOpened():
            ret_f, frame_f = cap_f.read()
            ret_r, frame_r = cap_r.read()
            
            if not ret_f or not ret_r:
                break
                
            timestamp = frame_idx / fps
            
            # Downsample raw 3840x3840 frames to 1024x1024 for tracking to save VRAM and CPU
            frame_f_small = cv2.resize(frame_f, (1024, 1024))
            frame_r_small = cv2.resize(frame_r, (1024, 1024))
            
            # Project static viewports on CPU
            view_rider = proj_rider.project(frame_f_small, frame_r_small, yaw=0, pitch=np.radians(-35), roll=0)
            view_kite = proj_kite.project(frame_f_small, frame_r_small, yaw=np.radians(180), pitch=np.radians(35), roll=0)
            
            is_keyframe = (frame_idx % step_frames == 0)
            rider_yaw, rider_pitch = None, None
            kite_yaw, kite_pitch = None, None
            rider_det = None
            kite_det = None
            scenery_dets = []
            
            # 1. Run YOLOv8 on keyframes (1 FPS) to re-verify/re-init trackers
            if is_keyframe:
                res_rider = self.model(view_rider, verbose=False, device=self.device)[0]
                res_kite = self.model(view_kite, verbose=False, device=self.device)[0]
                
                # Check rider
                for box in res_rider.boxes:
                    cls_id = int(box.cls[0])
                    conf = float(box.conf[0])
                    if cls_id in [0, 37]: # Person/Surfboard
                        if rider_det is None or conf > rider_det['conf']:
                            rider_det = {'conf': conf, 'box': box.xyxy[0].tolist(), 'type': 'rider'}
                    elif cls_id == 8: # Boat
                        scenery_dets.append({'conf': conf, 'type': 'boat'})
                        
                # Check kite
                for box in res_kite.boxes:
                    cls_id = int(box.cls[0])
                    conf = float(box.conf[0])
                    if cls_id == 38: # Kite
                        if kite_det is None or conf > kite_det['conf']:
                            kite_det = {'conf': conf, 'box': box.xyxy[0].tolist(), 'type': 'kite'}
                    elif cls_id in [0, 8]: # Other kiters/boats
                        scenery_dets.append({'conf': conf, 'type': 'scenery_object'})
                
                # (Re)-init tracker_rider
                if rider_det is not None:
                    box = rider_det['box']
                    x_c = (box[0] + box[2]) / 2.0
                    y_c = (box[1] + box[3]) / 2.0
                    # Convert to spherical
                    yaw_off = (x_c - 320.0) / 320.0 * (fov_rad / 2.0)
                    pitch_off = -(y_c - 320.0) / 320.0 * (fov_rad / 2.0)
                    rider_yaw = 0.0 + yaw_off
                    rider_pitch = np.radians(-35) + pitch_off
                    
                    last_rider_yaw, last_rider_pitch = rider_yaw, rider_pitch
                    
                    # Clamp bounding box coordinates to image boundaries for MIL tracker init
                    # Add 20% context padding around YOLO detection for tracking stability
                    w_raw = box[2] - box[0]
                    h_raw = box[3] - box[1]
                    pad_w = int(w_raw * 0.2)
                    pad_h = int(h_raw * 0.2)
                    
                    x1 = max(0, min(639, int(box[0] - pad_w)))
                    y1 = max(0, min(639, int(box[1] - pad_h)))
                    x2 = max(0, min(639, int(box[2] + pad_w)))
                    y2 = max(0, min(639, int(box[3] + pad_h)))
                    w = max(10, x2 - x1)
                    h = max(10, y2 - y1)
                    if x1 + w > 640: x1 = 640 - w
                    if y1 + h > 640: y1 = 640 - h
                    
                    # Reset tracker to clear any drift
                    tracker_rider = cv2.TrackerMIL_create()
                    tracker_rider.init(view_rider, (x1, y1, w, h))
                else:
                    tracker_rider = None
                    
                # (Re)-init tracker_kite
                if kite_det is not None:
                    box = kite_det['box']
                    x_c = (box[0] + box[2]) / 2.0
                    y_c = (box[1] + box[3]) / 2.0
                    # Convert to spherical
                    yaw_off = (x_c - 320.0) / 320.0 * (fov_rad / 2.0)
                    pitch_off = -(y_c - 320.0) / 320.0 * (fov_rad / 2.0)
                    kite_yaw = np.radians(180) + yaw_off
                    kite_pitch = np.radians(35) + pitch_off
                    
                    last_kite_yaw, last_kite_pitch = kite_yaw, kite_pitch
                    
                    # Clamp bounding box coordinates to image boundaries for MIL tracker init
                    # Add 20% context padding around YOLO detection for tracking stability
                    w_raw = box[2] - box[0]
                    h_raw = box[3] - box[1]
                    pad_w = int(w_raw * 0.2)
                    pad_h = int(h_raw * 0.2)
                    
                    x1 = max(0, min(639, int(box[0] - pad_w)))
                    y1 = max(0, min(639, int(box[1] - pad_h)))
                    x2 = max(0, min(639, int(box[2] + pad_w)))
                    y2 = max(0, min(639, int(box[3] + pad_h)))
                    w = max(10, x2 - x1)
                    h = max(10, y2 - y1)
                    if x1 + w > 640: x1 = 640 - w
                    if y1 + h > 640: y1 = 640 - h
                    
                    # Reset tracker
                    tracker_kite = cv2.TrackerMIL_create()
                    tracker_kite.init(view_kite, (x1, y1, w, h))
                else:
                    tracker_kite = None
            else:
                # 2. Intermediate frame tracking via OpenCV tracker on static coordinates
                if tracker_rider is not None:
                    track_ok, bbox = tracker_rider.update(view_rider)
                    if track_ok:
                        x_c = bbox[0] + bbox[2] / 2.0
                        y_c = bbox[1] + bbox[3] / 2.0
                        yaw_off = (x_c - 320.0) / 320.0 * (fov_rad / 2.0)
                        pitch_off = -(y_c - 320.0) / 320.0 * (fov_rad / 2.0)
                        rider_yaw = 0.0 + yaw_off
                        rider_pitch = np.radians(-35) + pitch_off
                        last_rider_yaw, last_rider_pitch = rider_yaw, rider_pitch
                        rider_det = {'conf': 0.8, 'type': 'rider'}
                    else:
                        tracker_rider = None
                        
                if tracker_kite is not None:
                    track_ok, bbox = tracker_kite.update(view_kite)
                    if track_ok:
                        x_c = bbox[0] + bbox[2] / 2.0
                        y_c = bbox[1] + bbox[3] / 2.0
                        yaw_off = (x_c - 320.0) / 320.0 * (fov_rad / 2.0)
                        pitch_off = -(y_c - 320.0) / 320.0 * (fov_rad / 2.0)
                        kite_yaw = np.radians(180) + yaw_off
                        kite_pitch = np.radians(35) + pitch_off
                        last_kite_yaw, last_kite_pitch = kite_yaw, kite_pitch
                        kite_det = {'conf': 0.8, 'type': 'kite'}
                    else:
                        tracker_kite = None
            
            # Save frame data with absolute angles (30 Hz) - leave lost frames as None for post-scan interpolation
            timeline.append({
                'timestamp': timestamp,
                'frame_idx': frame_idx,
                'rider': rider_det,
                'rider_yaw': rider_yaw,       # None if lost
                'rider_pitch': rider_pitch,   # None if lost
                'kite': kite_det,
                'kite_yaw': kite_yaw,         # None if lost
                'kite_pitch': kite_pitch,     # None if lost
                'scenery': len(scenery_dets) > 0 or not is_keyframe, # keep scenery continuity
                'scenery_count': len(scenery_dets)
            })
            
            # Explicit cleanup of frames
            del frame_f_small, frame_r_small, view_rider, view_kite
            
            # GC/Empty cache less frequently (every 100 frames) to speed up sequential loop
            if frame_idx % 100 == 0:
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                gc.collect()
                
            if progress_callback and frame_idx % 30 == 0:
                progress_callback(timestamp / duration)
                
            frame_idx += 1
            
        # 3. Post-process: interpolate target tracking gaps (None values) in the timeline
        for key in ['rider_yaw', 'rider_pitch', 'kite_yaw', 'kite_pitch']:
            valid_indices = [i for i, entry in enumerate(timeline) if entry[key] is not None]
            
            if not valid_indices:
                # If target was never detected, default to standard camera directions
                default_val = 0.0
                if key == 'rider_pitch': default_val = np.radians(-35)
                elif key == 'kite_yaw': default_val = np.radians(180)
                elif key == 'kite_pitch': default_val = np.radians(35)
                
                for entry in timeline:
                    entry[key] = default_val
                continue
                
            # Back-fill the beginning of the video
            first_idx = valid_indices[0]
            for i in range(first_idx):
                timeline[i][key] = timeline[first_idx][key]
                
            # Forward-fill the end of the video
            last_idx = valid_indices[-1]
            for i in range(last_idx + 1, len(timeline)):
                timeline[i][key] = timeline[last_idx][key]
                
            # Linearly interpolate gaps in between detections
            for k in range(len(valid_indices) - 1):
                idx1 = valid_indices[k]
                idx2 = valid_indices[k+1]
                val1 = timeline[idx1][key]
                val2 = timeline[idx2][key]
                
                is_yaw = 'yaw' in key
                
                for i in range(idx1 + 1, idx2):
                    weight = (i - idx1) / (idx2 - idx1)
                    if is_yaw:
                        # Shortest-path circular interpolation
                        diff = (val2 - val1 + np.pi) % (2.0 * np.pi) - np.pi
                        timeline[i][key] = val1 + weight * diff
                    else:
                        timeline[i][key] = val1 + weight * (val2 - val1)
                        
        cap_f.release()
        cap_r.release()
        return timeline


def quat_to_matrix(q):
    w, x, y, z = q
    norm = np.sqrt(w*w + x*x + y*y + z*z)
    if norm < 1e-6:
        return np.eye(3, dtype=np.float32)
    w /= norm
    x /= norm
    y /= norm
    z /= norm
    return np.array([
        [1 - 2*y**2 - 2*z**2, 2*x*y - 2*w*z, 2*x*z + 2*w*y],
        [2*x*y + 2*w*z, 1 - 2*x**2 - 2*z**2, 2*y*z - 2*w*x],
        [2*x*z - 2*w*y, 2*y*z + 2*w*x, 1 - 2*x**2 - 2*y**2]
    ], dtype=np.float32)

class HighlightGenerator:
    def __init__(self, timeline, video_path_front=None, W_out=1920, H_out=1080, format_type="YT"):
        self.timeline = timeline
        self.format_type = format_type
        self.video_path_front = video_path_front
        self.camera_metadata = None
        
        # Clean and interpolate timeline angles to fill in missing detections
        self._clean_and_interpolate_timeline()
        
        if video_path_front:
            self._try_load_gyroflow_metadata()
            
        # Set resolutions based on output format
        if format_type == "Instagram":
            self.W_out = 1080
            self.H_out = 1920
            self.fov = 85
        else: # YouTube
            self.W_out = 1920
            self.H_out = 1080
            self.fov = 95
            
        self.projector = FisheyeProjector(self.W_out, self.H_out, fov_deg=self.fov)

    def _try_load_gyroflow_metadata(self):
        if not self.video_path_front:
            return
            
        base, ext = os.path.splitext(self.video_path_front)
        match = re.search(r"temp_front_(VID_.*)\.mp4$", os.path.basename(self.video_path_front))
        if match:
            gyroflow_path = os.path.join(os.path.dirname(self.video_path_front), match.group(1) + ".gyroflow")
        else:
            gyroflow_path = base + ".gyroflow"
            
        if not os.path.exists(gyroflow_path):
            # Try searching the directory for any .gyroflow file
            dir_name = os.path.dirname(self.video_path_front) or "."
            gyro_files = glob.glob(os.path.join(dir_name, "*.gyroflow"))
            if len(gyro_files) == 1:
                gyroflow_path = gyro_files[0]
            else:
                vid_files = glob.glob(os.path.join(dir_name, "VID_*.gyroflow"))
                if vid_files:
                    gyroflow_path = vid_files[0]
                    
        if not os.path.exists(gyroflow_path):
            print(f"[Gyroflow] No project file found at {gyroflow_path}. Using fallback visual stabilization.")
            return
            
        print(f"[Gyroflow] Found project file at {gyroflow_path}")
        
        camera_json = "/mnt/c/Users/me/.gemini/antigravity/scratch/camera.json"
        gyroflow_exe = "/mnt/c/Users/me/.gemini/antigravity/scratch/Gyroflow/Gyroflow.exe"
        if not os.path.exists(gyroflow_exe):
            print(f"[Gyroflow] Executable not found at {gyroflow_exe}. Fallback to visual stabilization.")
            return
            
        try:
            wslpath_res1 = subprocess.run(['wslpath', '-w', gyroflow_path], capture_output=True, text=True, check=True)
            win_gyroflow_path = wslpath_res1.stdout.strip()
            
            print(f"[Gyroflow] Exporting stabilized orientation metadata to camera.json...")
            cmd = [
                gyroflow_exe,
                win_gyroflow_path,
                '--export-metadata',
                f'3:{camera_json}',
                '-f'
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0:
                print(f"[Gyroflow] CLI failed with exit code {res.returncode}. Stderr: {res.stderr}")
                return
                
            if os.path.exists(camera_json):
                print(f"[Gyroflow] Successfully loaded stabilized orientations from camera.json")
                with open(camera_json, 'r') as f:
                    self.camera_metadata = json.load(f)
            else:
                print(f"[Gyroflow] Export failed, camera.json not found.")
        except Exception as e:
            print(f"[Gyroflow] Error running Gyroflow CLI: {e}")

    def find_matching_timestamp(self, video_path_front, template_path):
        import cv2
        import numpy as np
        
        print(f"Loading template: {template_path}")
        tpl = cv2.imread(template_path)
        if tpl is None:
            print("Warning: Template image could not be loaded. Defaulting start time to 0.0s.")
            return 0.0
            
        # Resize template to keep matching fast
        h_tpl, w_tpl = tpl.shape[:2]
        max_dim = 640
        if max(h_tpl, w_tpl) > max_dim:
            scale = max_dim / max(h_tpl, w_tpl)
            tpl = cv2.resize(tpl, (0, 0), fx=scale, fy=scale)
            
        # Initialize ORB detector
        orb = cv2.ORB_create(nfeatures=1500)
        kp_tpl, des_tpl = orb.detectAndCompute(tpl, None)
        if des_tpl is None:
            print("Warning: No features found in template. Defaulting start time to 0.0s.")
            return 0.0
            
        bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        
        cap = cv2.VideoCapture(video_path_front)
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if fps <= 0:
            fps = 30.0
            
        # Scan every 2 seconds to be extremely fast and responsive
        step = int(fps * 2.0)
        
        best_t = 0.0
        max_good_matches = 0
        
        # Project a vertical view looking down at the rider (yaw=0, pitch=-35 degrees)
        # matching the typical phone/harness camera crop
        yaw = 0.0
        pitch = np.radians(-35)
        
        temp_projector = FisheyeProjector(640, 640, fov_deg=85, force_cpu=True)
        
        frame_idx = 0
        while True:
            if frame_idx > 0:
                for _ in range(step - 1):
                    cap.grab()
            ret, frame = cap.read()
            if not ret:
                break
                
            frame_small = cv2.resize(frame, (1024, 1024))
            view = temp_projector.project(frame_small, frame_small, yaw=yaw, pitch=pitch, roll=0)
            
            kp_v, des_v = orb.detectAndCompute(view, None)
            if des_v is not None:
                matches = bf.match(des_tpl, des_v)
                # Keep only high quality matches (distance < 50)
                good_matches = [m for m in matches if m.distance < 50.0]
                
                match_count = len(good_matches)
                if match_count > max_good_matches:
                    max_good_matches = match_count
                    best_t = frame_idx / fps
                    
            frame_idx += step
            
        cap.release()
        print(f"Best template match found at t = {best_t:.2f}s with {max_good_matches} matched features.")
        return best_t

    def _clean_and_interpolate_timeline(self):
        if not self.timeline:
            return
            
        # 1. Fill rider
        last_rider = (0.0, np.radians(-35)) # default
        for entry in self.timeline:
            if entry.get('rider_yaw') is not None:
                last_rider = (entry['rider_yaw'], entry['rider_pitch'])
                break
        for entry in self.timeline:
            if entry.get('rider_yaw') is not None:
                last_rider = (entry['rider_yaw'], entry['rider_pitch'])
            else:
                entry['rider_yaw'] = last_rider[0]
                entry['rider_pitch'] = last_rider[1]
                
        # 2. Fill kite
        last_kite = (np.radians(180), np.radians(35)) # default
        for entry in self.timeline:
            if entry.get('kite_yaw') is not None:
                last_kite = (entry['kite_yaw'], entry['kite_pitch'])
                break
        for entry in self.timeline:
            if entry.get('kite_yaw') is not None:
                last_kite = (entry['kite_yaw'], entry['kite_pitch'])
            else:
                entry['kite_yaw'] = last_kite[0]
                entry['kite_pitch'] = last_kite[1]

    def get_target_angles_for_frame(self, frame_idx, seg_type, fps):
        timestamp = frame_idx / fps
        
        # Find the timeline entries surrounding this timestamp
        before = None
        after = None
        for entry in self.timeline:
            if entry['timestamp'] <= timestamp:
                before = entry
            if entry['timestamp'] >= timestamp and after is None:
                after = entry
                break
                
        if before is None and after is None:
            if seg_type == 'rider': return 0.0, np.radians(-35)
            elif seg_type == 'kite': return np.radians(180), np.radians(35)
            else: return np.radians(90), 0.0
            
        if before is None: before = after
        if after is None: after = before
        
        yaw_key = 'rider_yaw' if seg_type == 'rider' else ('kite_yaw' if seg_type == 'kite' else None)
        pitch_key = 'rider_pitch' if seg_type == 'rider' else ('kite_pitch' if seg_type == 'kite' else None)
        
        if seg_type == 'scenery' or yaw_key is None or before[yaw_key] is None or after[yaw_key] is None:
            # Scenery: perform a slow, dynamic horizontal sweep (pan) over the entire video
            total_duration = self.timeline[-1]['timestamp'] if self.timeline else 300.0
            pan_yaw = np.radians(60) + (timestamp / total_duration) * np.radians(60)
            return pan_yaw, 0.0
            
        # Interpolate between keyframes
        t_diff = after['timestamp'] - before['timestamp']
        if t_diff < 0.01:
            return before[yaw_key], before[pitch_key]
            
        weight = (timestamp - before['timestamp']) / t_diff
        
        yaw_b = before[yaw_key]
        yaw_a = after[yaw_key]
        
        # Shortest path circular interpolation for yaw
        diff = (yaw_a - yaw_b + np.pi) % (2.0 * np.pi) - np.pi
        yaw_interp = yaw_b + weight * diff
        pitch_interp = before[pitch_key] + weight * (after[pitch_key] - before[pitch_key])
        
        return yaw_interp, pitch_interp

    def plan_highlights(self, target_duration, p_rider=0.2, p_kite=0.3, p_scenery=0.5):
        """
        Plans highlight segments matching focus percentages.
        """
        # Slices of 5 seconds each (or smaller if timeline is short)
        clip_len = min(5.0, len(self.timeline))
        if clip_len <= 0:
            return []
            
        num_clips = max(1, int(target_duration / clip_len))
        
        n_rider = max(0, int(num_clips * p_rider))
        n_kite = max(0, int(num_clips * p_kite))
        n_scenery = max(0, num_clips - n_rider - n_kite)
        if n_rider + n_kite + n_scenery == 0:
            n_scenery = 1
            
        # Rank timeline segments by scores
        rider_clips = []
        kite_clips = []
        scenery_clips = []
        
        window_size = int(clip_len)
        if window_size <= 0:
            return []
        
        for i in range(len(self.timeline) - window_size + 1):
            window = self.timeline[i : i + window_size]
            t_start = window[0]['timestamp']
            
            # Scores
            rider_score = sum(w['rider']['conf'] if w['rider'] else 0 for w in window)
            kite_score = sum(w['kite']['conf'] if w['kite'] else 0 for w in window)
            scenery_score = sum(w['scenery_count'] + (0.5 if w['scenery'] else 0) for w in window)
            
            rider_clips.append((rider_score, t_start, 'rider'))
            kite_clips.append((kite_score, t_start, 'kite'))
            scenery_clips.append((scenery_score, t_start, 'scenery'))
            
        # Sort and select best non-overlapping segments
        rider_clips.sort(reverse=True, key=lambda x: x[0])
        kite_clips.sort(reverse=True, key=lambda x: x[0])
        scenery_clips.sort(reverse=True, key=lambda x: x[0])
        
        selected_segments = []
        used_times = []
        
        def is_overlap(t):
            return any(abs(t - ut) < clip_len for ut in used_times)
            
        # Select rider
        for score, t, cat in rider_clips:
            if len(selected_segments) >= n_rider:
                break
            if not is_overlap(t):
                selected_segments.append({'start': t, 'end': t + clip_len, 'type': 'rider'})
                used_times.append(t)
                
        # Select kite
        for score, t, cat in kite_clips:
            if len(selected_segments) >= (n_rider + n_kite):
                break
            if not is_overlap(t):
                selected_segments.append({'start': t, 'end': t + clip_len, 'type': 'kite'})
                used_times.append(t)
                
        # Select scenery
        for score, t, cat in scenery_clips:
            if len(selected_segments) >= num_clips:
                break
            if not is_overlap(t):
                selected_segments.append({'start': t, 'end': t + clip_len, 'type': 'scenery'})
                used_times.append(t)
                
        # Sort chronologically
        selected_segments.sort(key=lambda x: x['start'])
        return selected_segments

    def render_video(self, video_path_front, video_path_rear, segments, output_path, progress_callback=None):
        """
        Renders the reframed clips, applying horizon stabilization and smooth camera motions.
        """
        cap_f = cv2.VideoCapture(video_path_front)
        cap_r = cv2.VideoCapture(video_path_rear)
        fps = cap_f.get(cv2.CAP_PROP_FPS)
        
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out_writer = cv2.VideoWriter(output_path, fourcc, fps, (self.W_out, self.H_out))
        
        total_frames_to_render = sum(int((seg['end'] - seg['start']) * fps) for seg in segments)
        rendered_frames = 0
        
        # State variables for panning and stabilization
        last_yaw = None
        last_pitch = None
        last_roll = None
        
        for seg_idx, seg in enumerate(segments):
            start_frame = int(seg['start'] * fps)
            end_frame = int(seg['end'] * fps)
            
            cap_f.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
            cap_r.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
            
            # Reset smoothing on segment boundaries to perform a clean CUT
            first_frame_in_segment = True
            
            for f_idx in range(start_frame, end_frame):
                ret_f, frame_f = cap_f.read()
                ret_r, frame_r = cap_r.read()
                
                if not ret_f or not ret_r:
                    break
                    
                if self.camera_metadata and f_idx < len(self.camera_metadata):
                    m = self.camera_metadata[f_idx]
                    org_quat = m['org_quat']
                    stab_quat = m['stab_quat']
                    
                    R_raw = quat_to_matrix(org_quat)
                    R_stab = quat_to_matrix(stab_quat)
                    
                    # Permutation matrix for Perm: (0, 2, 1) | Signs: (1, -1, -1)
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
                    
                    R_raw_proj = P @ R_raw @ P.T
                    R_stab_proj = P @ R_stab @ P.T
                    
                    # 1. Get relative target coordinates from the timeline
                    target_yaw, target_pitch = self.get_target_angles_for_frame(f_idx, seg['type'], fps)
                    
                    # 2. Convert target direction to unit vector in camera body coordinates
                    v_cam = np.array([
                        np.sin(target_yaw) * np.cos(target_pitch),
                        -np.sin(target_pitch),
                        np.cos(target_yaw) * np.cos(target_pitch)
                    ], dtype=np.float32)
                    
                    # 3. Rotate to stabilized world frame (using calibrated stabilized coordinates)
                    v_stab = R_roll.T @ R_stab_proj @ R_raw_proj.T @ v_cam
                    
                    # 4. Extract yaw/pitch in stabilized world coordinates
                    target_yaw_stab = np.arctan2(v_stab[0], v_stab[2])
                    target_pitch_stab = -np.arcsin(np.clip(v_stab[1], -1.0, 1.0))
                    
                    # 5. Smooth the tracking viewpoint (cinematic pans)
                    if first_frame_in_segment or last_yaw is None:
                        yaw = target_yaw_stab
                        pitch = target_pitch_stab
                        first_frame_in_segment = False
                    else:
                        diff_yaw = (target_yaw_stab - last_yaw + np.pi) % (2.0 * np.pi) - np.pi
                        yaw = last_yaw + 0.05 * diff_yaw
                        pitch = last_pitch + 0.05 * (target_pitch_stab - last_pitch)
                        
                    last_yaw = (yaw + np.pi) % (2.0 * np.pi) - np.pi
                    last_pitch = pitch
                    
                    # 6. Construct R_look rotation matrix (Yaw @ Pitch)
                    cy, sy = np.cos(yaw), np.sin(yaw)
                    cp, sp = np.cos(pitch), np.sin(pitch)
                    R_yaw_look = np.array([
                        [cy, 0, sy],
                        [0, 1, 0],
                        [-sy, 0, cy]
                    ], dtype=np.float32)
                    R_pitch_look = np.array([
                        [1, 0, 0],
                        [0, cp, -sp],
                        [0, sp, cp]
                    ], dtype=np.float32)
                    R_look = R_yaw_look @ R_pitch_look
                    
                    # 7. Final rotation matrix for the projector: R = R_raw_proj @ R_stab_proj.T @ R_roll @ R_look
                    R_final = R_raw_proj @ R_stab_proj.T @ R_roll @ R_look
                    
                    output_frame = self.projector.project(frame_f, frame_r, R=R_final)
                else:
                    # Fallback to visual horizon lock & deadband panning if no Gyroflow data is present
                    # 1. Get the pre-computed target yaw/pitch from timeline (open-loop!)
                    target_yaw, target_pitch = self.get_target_angles_for_frame(f_idx, seg['type'], fps)
                    raw_roll = HorizonStabilizer.estimate_roll(frame_f, frame_r)
                    
                    # Perform clean cut on segment start or first frame of video
                    if first_frame_in_segment or last_yaw is None:
                        last_yaw = target_yaw
                        last_pitch = target_pitch
                        last_roll = raw_roll
                        last_target_yaw = target_yaw
                        last_target_pitch = target_pitch
                        first_frame_in_segment = False
                    
                    # Horizon stabilization: set the output roll to raw_roll instantly to keep it level.
                    # Use a light low-pass (alpha_roll = 0.80) to filter out single-frame outliers.
                    roll = last_roll + 0.80 * (raw_roll - last_roll)
                    
                    # --- Deadband Panning Logic ---
                    # 1. Update relative viewpoint to counteract camera body rotation since last frame
                    body_rot_yaw = (target_yaw - last_target_yaw + np.pi) % (2.0 * np.pi) - np.pi
                    body_rot_pitch = target_pitch - last_target_pitch
                    
                    # Base viewpoint that stays stationary in world coordinates
                    locked_yaw = last_yaw + body_rot_yaw
                    locked_pitch = last_pitch + body_rot_pitch
                    
                    # 2. Measure the target's displacement from the center of our viewport
                    disp_yaw = (target_yaw - locked_yaw + np.pi) % (2.0 * np.pi) - np.pi
                    disp_pitch = target_pitch - locked_pitch
                    
                    # Deadband threshold (10 degrees)
                    deadband = np.radians(10.0)
                    
                    # Apply deadband correction for yaw
                    if abs(disp_yaw) > deadband:
                        # Target is outside deadband! Pan the camera slowly to bring it back inside
                        pan_dir = np.sign(disp_yaw)
                        excess = abs(disp_yaw) - deadband
                        # We pan slowly (alpha = 0.05) to reduce the excess displacement
                        yaw = locked_yaw + 0.05 * pan_dir * excess
                    else:
                        # Target is inside deadband! Keep the camera viewpoint perfectly locked in world space
                        yaw = locked_yaw
                        
                    # Apply deadband correction for pitch
                    if abs(disp_pitch) > deadband:
                        pan_dir = np.sign(disp_pitch)
                        excess = abs(disp_pitch) - deadband
                        pitch = locked_pitch + 0.05 * pan_dir * excess
                    else:
                        pitch = locked_pitch
                    
                    # Update tracking states
                    last_yaw = (yaw + np.pi) % (2.0 * np.pi) - np.pi
                    last_pitch = pitch
                    last_roll = roll
                    last_target_yaw = target_yaw
                    last_target_pitch = target_pitch
                    
                    # 2. Render high-resolution output frame
                    output_frame = self.projector.project(frame_f, frame_r, yaw, pitch, roll)
                out_writer.write(output_frame)
                
                # Explicit cleanup of PyTorch/CUDA cache references
                del frame_f, frame_r, output_frame
                
                rendered_frames += 1
                if progress_callback and rendered_frames % 10 == 0:
                    progress_callback(rendered_frames / total_frames_to_render)
                    
        cap_f.release()
        cap_r.release()
        out_writer.release()

    @staticmethod
    def mix_audio(video_path, source_audio_video, music_path, output_path, mix_music_ratio=0.7, mix_bg_ratio=0.3):
        """
        Uses FFmpeg to clip, mix, and set volume levels for background and music audio.
        """
        # Get video duration
        cmd_dur = [
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration', 
            '-of', 'default=noprint_wrappers=1:nokey=1', video_path
        ]
        res = subprocess.run(cmd_dur, capture_output=True, text=True)
        try:
            duration = float(res.stdout.strip())
        except ValueError:
            duration = 30.0 # fallback
            
        # Check if source video actually has an audio stream
        cmd_has_audio = [
            'ffprobe', '-v', 'error', '-select_streams', 'a',
            '-show_entries', 'stream=codec_type', '-of', 'default=nw=1:nk=1',
            source_audio_video
        ]
        has_audio_res = subprocess.run(cmd_has_audio, capture_output=True, text=True)
        has_audio = bool(has_audio_res.stdout.strip())
        
        # FFmpeg audio filter graph:
        # If the source video has audio, we mix it with the music.
        # Otherwise, we just map the music track.
        if has_audio:
            cmd_mix = [
                'ffmpeg', '-y',
                '-i', video_path,                 # Input 0: Reframed Video
                '-i', source_audio_video,        # Input 1: Original recording for background audio
                '-i', music_path,                 # Input 2: Soundtrack music
                '-filter_complex', 
                f"[1:a]volume={mix_bg_ratio}[bg];"
                f"[2:a]atrim=end={duration},volume={mix_music_ratio}[music];"
                f"[bg][music]amix=inputs=2:duration=first[a]",
                '-map', '0:v',                    # Take video from reframed input
                '-map', '[a]',                    # Take mixed audio
                '-c:v', 'copy',                   # Copy video stream
                '-c:a', 'aac', '-b:a', '192k',    # Encode audio
                output_path
            ]
        else:
            cmd_mix = [
                'ffmpeg', '-y',
                '-i', video_path,                 # Input 0: Reframed Video
                '-i', music_path,                 # Input 1: Soundtrack music
                '-filter_complex', 
                f"[1:a]atrim=end={duration},volume={mix_music_ratio}[music]",
                '-map', '0:v',                    # Take video from reframed input
                '-map', '[music]',                # Take music audio
                '-c:v', 'copy',                   # Copy video stream
                '-c:a', 'aac', '-b:a', '192k',    # Encode audio
                output_path
            ]
            
        subprocess.run(cmd_mix, capture_output=True, check=True)


def find_video_pairs(directory):
    """
    Finds paired _00 and _10 video files in the specified directory, 
    or single files containing multiple video tracks (Insta360 X4/X5 multi-stream).
    Returns a list of dicts: [{'front': path, 'rear': path, 'prefix': name, 'single_file': bool}]
    """
    files = glob.glob(os.path.join(directory, "*.*"))
    pairs = {}
    
    # First pass: find standard paired files
    for f in files:
        base = os.path.basename(f)
        match_front = re.search(r"^(VID_.*)_00_(.*)$", base, re.IGNORECASE)
        match_rear = re.search(r"^(VID_.*)_10_(.*)$", base, re.IGNORECASE)
        
        if match_front:
            prefix = match_front.group(1) + "_" + match_front.group(2)
            if prefix not in pairs:
                pairs[prefix] = {}
            pairs[prefix]['front'] = f
        elif match_rear:
            prefix = match_rear.group(1) + "_" + match_rear.group(2)
            if prefix not in pairs:
                pairs[prefix] = {}
            pairs[prefix]['rear'] = f
            
    valid_pairs = []
    # Find complete pairs
    for prefix, paths in pairs.items():
        if 'front' in paths and 'rear' in paths:
            valid_pairs.append({
                'prefix': prefix,
                'front': paths['front'],
                'rear': paths['rear'],
                'single_file': False
            })
            
    # Second pass: find single files that contain multiple video streams
    for f in files:
        base = os.path.basename(f)
        # Skip if it was already paired
        already_paired = False
        for vp in valid_pairs:
            if vp['front'] == f or vp['rear'] == f:
                already_paired = True
                break
        if already_paired:
            continue
            
        if f.lower().endswith(('.insv', '.mp4')):
            try:
                cmd = [
                    'ffprobe', '-v', 'error', '-select_streams', 'v',
                    '-show_entries', 'stream=index', '-of', 'default=nw=1:nk=1', f
                ]
                res = subprocess.run(cmd, capture_output=True, text=True)
                num_streams = len([line for line in res.stdout.split('\n') if line.strip()])
                if num_streams > 1:
                    prefix = os.path.splitext(base)[0]
                    valid_pairs.append({
                        'prefix': prefix,
                        'front': f,
                        'rear': f,
                        'single_file': True
                    })
            except Exception:
                pass
                
    return valid_pairs


def check_and_extract_streams(video_path, output_dir="."):
    """
    Checks if a video file has multiple video streams. If so, demuxes them to temporary files.
    """
    cmd = [
        'ffprobe', '-v', 'error', '-select_streams', 'v',
        '-show_entries', 'stream=index', '-of', 'default=nw=1:nk=1', video_path
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    try:
        num_streams = len([line for line in res.stdout.split('\n') if line.strip()])
    except Exception:
        num_streams = 1
        
    if num_streams > 1:
        prefix = os.path.splitext(os.path.basename(video_path))[0]
        temp_front = os.path.join(output_dir, f"temp_front_{prefix}.mp4")
        temp_rear = os.path.join(output_dir, f"temp_rear_{prefix}.mp4")
        
        # Only extract if they do not exist already (caching)
        if not os.path.exists(temp_front) or not os.path.exists(temp_rear):
            print(f"Demuxing and transcoding multi-stream video {video_path} using NVENC...")
            cmd_demux = [
                'ffmpeg', '-y', '-i', video_path,
                '-map', '0:v:0', '-c:v', 'h264_nvenc', '-preset', 'p1', '-cq', '19', '-r', '30000/1001', temp_front,
                '-map', '0:v:1', '-c:v', 'h264_nvenc', '-preset', 'p1', '-cq', '19', '-r', '30000/1001', temp_rear
            ]
            subprocess.run(cmd_demux, capture_output=True, check=True)
            
        return temp_front, temp_rear, True
    return video_path, None, False


def prepare_input_videos(front_path, rear_path=None, output_dir="."):
    """
    Prepares input paths by checking if they are the same multi-stream file.
    Returns (front, rear, is_temp)
    """
    if rear_path is None or front_path == rear_path:
        f, r, is_temp = check_and_extract_streams(front_path, output_dir)
        if is_temp:
            return f, r, True
    return front_path, rear_path, False
