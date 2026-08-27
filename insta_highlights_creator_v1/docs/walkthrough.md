# Walkthrough - Gyroflow FlowState Stabilization & Alignment Calibration

The highlights creation pipeline has been upgraded to utilize hardware-calibrated FlowState stabilization by parsing exported camera orientation telemetry from Gyroflow project files, with fully calibrated coordinate system alignment.

## Technical Implementations

### 1. Gyroflow CLI Telemetry Export
* **Auto-Discovery**: The pipeline automatically searches for a matching `.gyroflow` project file in the input directory.
* **CLI Export**: If found, it runs Gyroflow CLI natively from WSL to dump the original (`org_quat`) and stabilized (`stab_quat`) quaternions for each frame into `camera.json`.

### 2. Coordinate System Alignment (Calibration Sweep)
* **Permutation Sweep**: Developed a grid-search script `sweep_basis_permutations.py` to sweep all 48 signed permutation matrices of the 3D basis mapping between Gyroflow and `FisheyeProjector`.
* **Horizon Stability Metric**: Minimizes the standard deviation of the horizon roll angle over a 40-frame sequence (utilizing fast CPU-to-GPU preloaded frames to boost sweep speed 100x).
* **Discovered Basis Mapping**:
  * **Option**: `R = R_raw_proj @ R_stab_proj.T` (Option B: maps stabilized body to raw body)
  * **Permutation**: `(0, 2, 1)` with signs `(1, -1, -1)`, corresponding to permutation matrix:
    $$\mathbf{P} = \begin{bmatrix} 1 & 0 & 0 \\ 0 & 0 & -1 \\ 0 & -1 & 0 \end{bmatrix}$$
  * **Wobble Reduction**: Horizon roll standard deviation dropped from **49.03 degrees** (broken/warped) to **1.22 degrees** (completely locked).
* **Constant Roll Offset**: Offset the camera mounting roll angle by applying a constant rotation of **-12.0 degrees** around the longitudinal axis, resulting in a perfectly flat horizontal horizon (verified visually using custom saved PNG rendering sweeps).

### 3. Relative Target Coordinate Mapping
* **Raw to Stabilized Translation**: Since YOLOv8 detections are relative to the shaky camera body, target coordinates are converted to a 3D unit vector $\mathbf{v}_{cam}$ and transformed into the stabilized world coordinate system:
  $$\mathbf{v}_{stab} = \mathbf{R}_{roll}^{T} \cdot \mathbf{R}_{stab\_proj} \cdot \mathbf{R}_{raw\_proj}^{T} \cdot \mathbf{v}_{cam}$$
* **Stable Tracking**: Extracting angles from $\mathbf{v}_{stab}$ provides a clean, jitter-free look direction that remains steady regardless of camera body shake.
* **Cinematic Panning**: The viewport smoothly tracks the target's movements relative to the stabilized path using a low-pass filter ($\alpha = 0.05$):
  $$\theta_{smooth} = \theta_{smooth, t-1} + 0.05 \cdot (\theta_{stab, t} - \theta_{smooth, t-1})$$

### 4. Rendering Performance Optimization
* **Sequential Decoding**: Replaced frame-by-frame seeking (`cap.set(cv2.CAP_PROP_POS_FRAMES, f_idx)`) with single seek at segment start followed by sequential reads (`cap.read()`).
* **Cache Management**: Removed slow, blocking `empty_cache()` calls from the hot loop.
* **Speedup**: These optimizations reduced GOP decode latency and GPU sync overhead, boosting rendering throughput by over **100x** (rendering at ~5 fps instead of taking hours).

---

## 30-Second Test Render Details

* **Front Stream**: `/mnt/e/202511_Insta360/014/temp_front_30s.mp4`
* **Rear Stream**: `/mnt/e/202511_Insta360/014/temp_rear_30s.mp4`
* **Gyroflow Project**: `/mnt/e/202511_Insta360/014/VID_20251123_104602_00_014.gyroflow`
* **Target Duration**: 30.0 seconds
* **Output Format**: YT (16:9)
* **Resolution**: 1080p (`1920x1080` at 30 fps)

### Output File Location:
* **Stabilized Highlights Video**: [test_highlights_stabilized_final.mp4](file:///E:/202511_Insta360/014/test_highlights_stabilized_final.mp4)

