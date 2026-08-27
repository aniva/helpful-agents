# Stabilization Challenge - Camera on Kite Lines

This document defines the technical challenge, mathematical model, and current findings for stabilizing 360-degree footage recorded from a camera mounted on vibrating kite lines.

---

## 1. The Challenge Definition
* **Physical Context**: An Insta360 camera is suspended on kite lines during hydrofoil riding. The lines are under high tension and experience rapid, high-frequency physical vibrations (10–50 Hz) and body rotations from wind shear and kite movement.
* **Problem**: The raw video streams are extremely shaky and roll back and forth, making the footage unusable.
* **Goal**: Reframe a stable 4K perspective viewport tracking the rider, with a flat horizon and all high-frequency line vibrations cancelled out.

---

## 2. Input Data Streams

### Video Containers
* **Files**: Twin `.insv` or combined dual-stream HEVC videos.
* **Resolution**: $3840 \times 3840$ circular fisheye per lens.
* **Frame Rate**: Variable Frame Rate (VFR) around 29.97 fps.

### Telemetry (IMU)
* **Frequency**: ~1000 Hz (1 sample per millisecond).
* **Parser**: `telemetry-parser` (extracts native gyroscope and accelerometer registers).
* **Format**:
  ```python
  {'timestamp_ms': -3473.57, 'gyro': (gx, gy, gz), 'accl': (ax, ay, az)}
  ```
  * `gyro` values are in **degrees per second**.
  * `accl` values are in **m/s²**.

---

## 3. Mathematical Model

### A. Output Ray Projection (Fisheye to Perspective)
For a target canvas of size $W_{out} \times H_{out}$ at a focal length $f_{cam} = 1.0 / \tan(\text{FOV} / 2)$:
1. Each canvas pixel $(u, v)$ maps to a local 3D direction vector:
   $$\mathbf{v}_{local} = \text{Normalize}\left( \frac{u - W/2}{W/2}, -\frac{v - H/2}{W/2}, f_{cam} \right)$$
2. Rotate the ray grid by the virtual camera's relative orientation relative to the camera body:
   $$\mathbf{v}_{body} = \mathbf{R}_{yaw} \mathbf{R}_{pitch} \mathbf{R}_{roll} \times \mathbf{v}_{local}$$
3. Map $\mathbf{v}_{body} = (x_b, y_b, z_b)$ to the circular sensor coordinates $(u_s, v_s)$ using the equidistant fisheye model:
   $$\theta = \arccos(z_b), \quad r = f_{lens} \cdot \theta, \quad \alpha = \arctan2(y_b, x_b)$$
   $$u_s = c_x + r \cos(\alpha), \quad v_s = c_y + r \sin(\alpha)$$

### B. IMU FlowState Stabilization
To cancel camera rotation, we must rotate the viewpoint in the opposite direction of the camera body's absolute orientation in the world.
1. **Euler Integration**:
   $$\theta_{body}(t) = \int_0^t \omega_{gyro}(t) \, dt$$
2. **Cancellation**:
   $$\text{yaw}(t) = \theta_{target\_yaw} - \theta_{body\_yaw}(t)$$
   $$\text{pitch}(t) = \theta_{target\_pitch} - \theta_{body\_pitch}(t)$$
   $$\text{roll}(t) = -\theta_{body\_roll}(t)$$

---

## 4. Key Debugging Findings

### A. Video Decoding Jitter (Solved)
* **Symptom**: Out-of-order decoding (frames jumping back and forth by 1 frame), producing high-frequency vibration even with a static relative viewpoint.
* **Cause**: Splitting raw VFR HEVC streams using copy containers (`-c copy`) breaks the PTS/DTS timestamps.
* **Solution**: Transcode the demuxed streams to H.264 at a **constant frame rate** (CFR, e.g., 29.97 fps) using GPU acceleration (`h264_nvenc`) before decoding.

### B. Integration Aliasing (Solved)
* **Symptom**: Sweeping all 16 sign and axis combinations in a static test video resulted in the same shaky output.
* **Root Cause**: Integrating the gyroscope data inside the 30 fps video loop (sampling only one IMU value every 33 ms) missed the high-frequency (20 Hz) vibration peaks, causing severe **mathematical aliasing**. 
* **Solution**: Integrate the gyroscope data at its **native 1000 Hz frequency** step-by-step from the start of the telemetry log to preserve all high-frequency vibrations, then look up the pre-integrated angles at the frame timestamps.

### C. Gimbal Lock & IMU Axis Permutations (Under Active Debugging)
* **Symptom**: Integrated angles produce a level horizon (correct Roll), but a distinct "circular shaking" remains.
* **Root Cause**: 
  1. 3D rotations are non-commutative. The correct world-to-body stabilization rotation order is Roll $\rightarrow$ Pitch $\rightarrow$ Yaw ($\mathbf{R}_{roll} \mathbf{R}_{pitch} \mathbf{R}_{yaw}$).
  2. The physical camera is mounted vertically upright, but the internal IMU sensor chip's axes relative to the camera body may be permuted (e.g. the motherboard is mounted sideways/upside-down inside the casing). 
* **Required Fix**: Run a sweep over all 6 possible 3D channel permutations of the gyroscope axes $(X, Y, Z) \to (\text{Yaw}, \text{Pitch}, \text{Roll})$ under the correct RPY rotation order to determine the motherboard's exact spatial alignment.

