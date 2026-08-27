# Gyroflow-Based Automatic Video Stabilization

This plan replaces the custom Integrated 1000 Hz Gyroscope stabilizer with a robust, fully automated Gyroflow-based stabilizer. It uses the manufacturer's exact, hardware-calibrated FlowState telemetry by parsing exported frame-by-frame quaternions.

---

## User Review Required

> [!IMPORTANT]
> The stabilization relies on a pre-existing `.gyroflow` project file matching the input video (e.g., `VID_20251123_104602_00_014.gyroflow` placed in the same folder as the raw `.insv` file). The user must first load the raw video in the Gyroflow GUI, perform synchronization, and save the project file. The pipeline then handles the rest of the extraction and rendering process automatically.

---

## Open Questions

None. The mathematical formulation has been verified with a 5-second test render and matches the physical world-to-body stabilization rotation order.

---

## Proposed Changes

### Video Stabilization Engine

We will update the core processing script to integrate Gyroflow's orientation quaternions directly into the rendering pipeline.

#### [MODIFY] [video_processor.py](file:///wsl.localhost/Ubuntu/home/me/repos/helpful-agents/insta_highlights_creator/video_processor.py)
* **Rotation Matrix Support**: Add support for passing a rotation matrix $\mathbf{R}$ directly to `FisheyeProjector.project`, `project_cpu`, and `project_cuda` (bypassing yaw/pitch/roll conversion when a matrix is available).
* **Automatic Metadata Export**:
  * In `HighlightGenerator.__init__`, check if a `.gyroflow` project file exists for the video.
  * If it exists, execute `Gyroflow.exe` from WSL to export the stabilized frame-by-frame camera orientations to a temporary `camera.json`.
  * Parse `camera.json` to load the list of original (`org_quat`) and stabilized (`stab_quat`) quaternions.
* **FlowState Cancellation & Viewport Tracking**:
  * In `HighlightGenerator.render_video`, for each frame:
    1. Extract `org_quat` and `stab_quat` from the parsed metadata.
    2. Convert both to $3 \times 3$ rotation matrices $\mathbf{R}_{raw}$ and $\mathbf{R}_{stab}$.
    3. Compute the tracking viewport rotation $\mathbf{R}_{look}$ based on the target (rider, kite, or scenery) yaw/pitch.
    4. Compute the combined rotation: $\mathbf{R} = \mathbf{R}_{raw}^{T} \cdot \mathbf{R}_{stab} \cdot \mathbf{R}_{look}$.
    5. Pass $\mathbf{R}$ directly to the projector.

---

## Verification Plan

### Automated Tests
* Run the highlights rendering pipeline on the 30-second test clips using the new stabilization method:
  `wsl -e sh -c "cd /home/me/repos/helpful-agents/insta_highlights_creator && /home/me/.local/bin/uv run python3 run.py --front /mnt/e/202511_Insta360/014/VID_20251123_104602_00_014.insv --preview --output /mnt/e/202511_Insta360/014/preview_stabilized.mp4"`

### Manual Verification
* Play back the generated preview video `/mnt/e/202511_Insta360/014/preview_stabilized.mp4` to confirm that the horizon is perfectly level, there is zero high-frequency camera shake, and tracking pans smoothly between the rider, kite, and scenery.
