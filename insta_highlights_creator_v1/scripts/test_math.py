import numpy as np
import cv2
import time

def precompute_grid(W_out, H_out, fov_deg):
    fov_rad = np.radians(fov_deg)
    # Horizontal focal length
    f_cam = 1.0 / np.tan(fov_rad / 2.0)
    
    # Create pixel grid
    u = np.arange(W_out)
    v = np.arange(H_out)
    u_grid, v_grid = np.meshgrid(u, v)
    
    # Normalize grid coordinates relative to optical center
    # x: right, y: down, z: forward
    x = (u_grid - W_out / 2.0) / (W_out / 2.0)
    y = (v_grid - H_out / 2.0) / (W_out / 2.0)
    z = np.full_like(x, f_cam)
    
    # Stack and normalize to unit sphere vectors
    vectors = np.stack([x, y, z], axis=-1)
    norms = np.linalg.norm(vectors, axis=-1, keepdims=True)
    vectors_n = vectors / norms
    return vectors_n

def get_rotation_matrix(yaw, pitch, roll):
    # yaw (Y-axis), pitch (X-axis), roll (Z-axis)
    cy, sy = np.cos(yaw), np.sin(yaw)
    cp, sp = np.cos(pitch), np.sin(pitch)
    cr, sr = np.cos(roll), np.sin(roll)
    
    # Standard Euler rotation matrices
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
    # Combined rotation: Yaw * Pitch * Roll
    return R_yaw @ R_pitch @ R_roll

def calculate_maps(vectors_n, yaw, pitch, roll, W_lens, H_lens, max_lens_fov_deg=200):
    H_out, W_out, _ = vectors_n.shape
    R = get_rotation_matrix(yaw, pitch, roll)
    
    # Rotate precomputed vectors (reshape to list of vectors, rotate, and reshape back)
    # vectors_rotated will have shape (H_out, W_out, 3)
    vectors_rot = np.dot(vectors_n, R.T)
    
    X_w = vectors_rot[..., 0]
    Y_w = vectors_rot[..., 1]
    Z_w = vectors_rot[..., 2]
    
    # Lens parameters: assume circular fisheye centers and radii
    # For a typical 1:1 circular fisheye video, center is at middle, radius is half-width
    c_x, c_y = W_lens / 2.0, H_lens / 2.0
    R_max = min(W_lens, H_lens) / 2.0
    alpha_max = np.radians(max_lens_fov_deg / 2.0) # angle corresponding to the circular boundary
    
    # --- Front Lens (Lens 0) ---
    # Optical axis is +Z
    alpha_0 = np.arccos(np.clip(Z_w, -1.0, 1.0))
    beta_0 = np.arctan2(Y_w, X_w)
    r_norm_0 = alpha_0 / alpha_max
    
    map_x0 = c_x + R_max * r_norm_0 * np.cos(beta_0)
    map_y0 = c_y + R_max * r_norm_0 * np.sin(beta_0)
    
    # --- Rear Lens (Lens 1) ---
    # Optical axis is -Z. Local coordinates: X' = -X, Y' = Y, Z' = -Z
    alpha_1 = np.arccos(np.clip(-Z_w, -1.0, 1.0))
    beta_1 = np.arctan2(Y_w, -X_w)
    r_norm_1 = alpha_1 / alpha_max
    
    map_x1 = c_x + R_max * r_norm_1 * np.cos(beta_1)
    map_y1 = c_y + R_max * r_norm_1 * np.sin(beta_1)
    
    # --- Blending Weights ---
    # Overlap region around Z_w = 0 (alpha_0 = 90 deg, alpha_1 = 90 deg)
    # Let's say overlap region is +/- 10 degrees around the equator
    delta = np.radians(10.0)
    eq_min = np.radians(90.0) - delta
    eq_max = np.radians(90.0) + delta
    
    # We blend using alpha_0 (angle from front lens optical axis)
    # W_front is 1 for alpha_0 < eq_min, 0 for alpha_0 > eq_max, and interpolates between
    w_front = np.clip((eq_max - alpha_0) / (2.0 * delta), 0.0, 1.0)
    # Convert weight to shape (H_out, W_out, 1) for broadcasting
    w_front = np.expand_dims(w_front, axis=-1)
    
    return map_x0.astype(np.float32), map_y0.astype(np.float32), \
           map_x1.astype(np.float32), map_y1.astype(np.float32), \
           w_front.astype(np.float32)

def test_performance():
    W_out, H_out = 640, 360  # Quick preview size
    W_lens, H_lens = 2880, 2880 # Standard Insta360 X4/X5 high res lens size
    
    print("Precomputing grid...")
    start = time.time()
    vectors_n = precompute_grid(W_out, H_out, fov_deg=90)
    print(f"Grid precomputed in {time.time() - start:.4f} seconds.")
    
    print("Calculating maps for first frame...")
    start = time.time()
    map_x0, map_y0, map_x1, map_y1, w_front = calculate_maps(
        vectors_n, yaw=np.radians(45), pitch=np.radians(10), roll=np.radians(-5),
        W_lens=W_lens, H_lens=H_lens
    )
    print(f"Map calculated in {time.time() - start:.4f} seconds.")
    
    # Simulate a run
    runs = 10
    start = time.time()
    for _ in range(runs):
        calculate_maps(
            vectors_n, yaw=np.radians(45), pitch=np.radians(10), roll=np.radians(-5),
            W_lens=W_lens, H_lens=H_lens
        )
    print(f"Average map calculation time over {runs} runs: {(time.time() - start) / runs:.4f} seconds.")

if __name__ == "__main__":
    test_performance()
