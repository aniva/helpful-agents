# Visual Pipeline Architecture - reframing & Stabilization

This document outlines all data flow, mathematical mappings, and encoding steps in the Insta360 highlights creation pipeline. 

---

## 1. Pipeline Flowchart

```mermaid
graph TD
    A["Raw .insv File (Dual-Stream HEVC)"] --> B["FFmpeg NVENC Demuxer & Transcoder"]
    B -->|Stream 0: Front Lens| C1["temp_front.mp4 (CFR H.264)"]
    B -->|Stream 1: Rear Lens| C2["temp_rear.mp4 (CFR H.264)"]
    
    C1 --> D["OpenCV cv2.VideoCapture (sequential frames)"]
    C2 --> D
    
    D -->|Raw Frame (3840x3840)| E["FisheyeProjector (GPU / PyTorch)"]
    
    subgraph Projection Engine [FisheyeProjector]
        F["1. Normalized 3D Output Ray Grid"] --> G["2. Rotation Matrix R(yaw, pitch, roll)"]
        G --> H["3. Rotated Directional Rays"]
        H --> I["4. Equidistant Lens Angle & Radius Mapping"]
        I --> J["5. 2D Sensor Coordinate Mesh Grid"]
    end
    
    E -->|Apply 2D Grid to Raw Frames| K["PyTorch grid_sample (Bilinear Interpolation)"]
    K -->|Rendered Frame (3840x2160 BGR)| L["FFmpeg Subprocess Pipe (stdin)"]
    L --> M["NVIDIA GPU NVENC H.264 Encoder"]
    M --> N["final_output.mp4"]
```

---

## 2. Step-by-Step Execution Details

### Node A & B: Input Demuxing
* **Input**: A single multi-stream `.insv` file containing two 4K HEVC streams (Front and Rear lenses) at variable frame rate.
* **Operation**: FFmpeg extracts stream 0 and stream 1, transcoding them to standard H.264 constant frame rate (CFR) at 29.97 fps using GPU acceleration:
  ```bash
  ffmpeg -y -i input.insv \
    -map 0:v:0 -c:v h264_nvenc -preset p1 -cq 19 -r 30000/1001 temp_front.mp4 \
    -map 0:v:1 -c:v h264_nvenc -preset p1 -cq 19 -r 30000/1001 temp_rear.mp4
  ```

### Node D: Frame Reader
* **Operation**: OpenCV opens `temp_front.mp4` and reads sequential frames using `cap.read()`.
* **Output**: A 3-channel BGR numpy array of size `3840x3840` per frame.

### Node E: Projection Engine (FisheyeProjector)
For a target output viewport of size $W_{out} \times H_{out}$ (e.g., $3840 \times 2160$ for 4K) at orientation $(\theta_{yaw}, \phi_{pitch}, \psi_{roll})$:
1. **Precomputed Ray Grid**: We map every output pixel $(u_x, v_y)$ to a 3D unit direction ray in camera local space:
   $$x = \frac{u_x - W_{out}/2}{W_{out}/2} \cdot \tan\left(\frac{\text{FOV}}{2}\right), \quad y = -\frac{v_y - H_{out}/2}{W_{out}/2} \cdot \tan\left(\frac{\text{FOV}}{2}\right), \quad z = 1.0$$
   $$\mathbf{v}_{local} = \frac{(x, y, z)}{\sqrt{x^2 + y^2 + z^2}}$$
2. **Rotation**: Rotate the ray grid on the GPU:
   $$\mathbf{v}_{body} = \mathbf{R}_z(\theta_{yaw}) \mathbf{R}_y(\phi_{pitch}) \mathbf{R}_x(\psi_{roll}) \times \mathbf{v}_{local}$$
3. **Fisheye Mapping**: Convert 3D body ray $(x_b, y_b, z_b)$ to 2D coordinates on the sensor circle:
   * Spherical angle from lens axis: $\theta = \arccos(z_b)$ (front) or $\theta = \arccos(-z_b)$ (rear).
   * Circular radius: $r = f \cdot \theta$.
   * Angle in transverse plane: $\alpha = \arctan2(y_b, x_b)$ (front) or $\alpha = \arctan2(y_b, -x_b)$ (rear).
   * Sensor coordinates: $u = u_c + r \cos(\alpha), \quad v = v_c + r \sin(\alpha)$.

### Node K: GPU Bilinear Interpolation
* **Operation**: PyTorch warps the raw $3840 \times 3840$ input frames using the normalized coordinate grid:
  ```python
  warp_front = F.grid_sample(t_front, cached_grid_0, mode='bilinear', align_corners=True)
  ```

### Node L & M: GPU Encoding Pipe
* **Operation**: Raw BGR24 frames are piped directly to FFmpeg to encode the final H.264 file on the GPU, avoiding CPU container compression:
  ```bash
  ffmpeg -y -f rawvideo -vcodec rawvideo -pix_fmt bgr24 -s 3840x2160 -r 29.97 -i - -c:v h264_nvenc final_output.mp4
  ```

---

## 3. Current Debugging Target: The "Every Second" Jitter

Because the mapping grid coordinates in **Node E** are **100% static and cached** (they never change during a static viewport render), the projection math itself cannot introduce frame-to-frame oscillations. 

The vibration must originate from:
1. **GOP/Keyframe Jumps in FFmpeg Transcoding (Node B)**: If the transcoding of the raw variable-frame-rate `.insv` file drops packets or misinterprets timestamps at I-frame boundaries (which occur exactly once a second), OpenCV will decode a jumpy sequence.
2. **OpenCV Decentered Crop Alignment**: If the circular center $(u_c, v_c)$ of the lens in the raw file is not exactly $1920, 1920$, any minor frame resizing or padding will cause projection distortion.
