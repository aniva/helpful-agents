# Automated Kitefoil Video Processing Pipeline

**Author:** Aniva

This project provides an automated, telemetry-driven video processing ecosystem designed to ingest, programmatically stitch, select action highlights, and stabilize dual-lens data from a custom mechanical kitefoil mount.

---

## Project Goals

* **Zero Friction Editing:** Eliminate manual keyframing and desktop app splicing by turning hours of raw multi-lens data into instant action summaries.
* **Telemetry Driven Selection:** Programmatically isolate high-value riding moments like hard carves, high-velocity runs, or jumps using hardware sensor anomalies.
* **Flawless Stabilization:** Achieve a perfectly level horizon across the full 360-degree sphere using physical IMU sensors rather than slower visual pixel guesses.
* **Interactive Zoom Previews:** Provide a commercial preview mode that generates sample frames across a range of focal lengths (f = 800 to 1280), letting users visually select the optimal camera zoom before starting the full 4K HEVC render pipeline.
* **Commercial Scalability:** Build a community footprint using open-source hardware assets while preparing a high-margin, low-overhead computing footprint for a future hybrid SaaS model.

---

## Architecture

```
[Raw X5 Dual Lens INSV Blocks]
               │
               ▼
┌──────────────────────────────┐
│  Insta360 Desktop Media SDK  │ ──> Headless Optical Flow Stitching
└──────────────┬───────────────┘     (Applies Lens Guard Profile matrices)
               │
               ▼
┌──────────────────────────────┐
│         Gyroflow CLI         │ ──> Native Equirectangular Horizon Leveling
└──────────────┬───────────────┘     (Zero custom lens profiles required)
               │
               ▼
┌──────────────────────────────┐
│    Telemetry Slicing Engine  │ ──> Python parsing of IMU data spikes
└──────────────┬───────────────┘     (Triggers lossless FFmpeg stream cuts)
               │
               ▼
[Final Stabilized Highlight Clips]
```

---

## Calibration & Framing Options (Kite Line Mount)

This pipeline is optimized for the **custom kite line mount** (camera suspended from the kite lines directly above the rider). The following focal length and tilt parameters have been calibrated to match:

*   **Projection Model:** Equidistant Fisheye (curves the horizon naturally, maximizing the field of view without edge stretching).
*   **Selected Stitch Engine:** Optical Flow (`optflow`) -- ensures deep neural frame alignment.
*   **Optimal Tilt Offset:** `-15.0°` downward pitch (points the camera slightly down from your chest coordinates to keep the board and underwater hydrofoil wing fully in frame).
*   **Vibration Correction:** Gaussian 1D kernel convolution (`sigma = 50` frames) to completely filter out high-frequency line shaking and mount vibration while smoothly following the kite's motion.

### Tested Focal Lengths (`f`) for 4K UHD (3840x2160):
*   `f = 800`: Super-Wide (rider occupies ~30% height, maximum horizon/kite view).
*   `f = 920`: Wide (rider occupies ~35% height).
*   **`f = 1160` (Optimal/Selected):** Perfect balance (rider occupies ~40% height, showing head to foil wing clearly).
*   `f = 1280`: Medium-Close (rider occupies ~45% height).

---

## Development Plan

* **Phase 1 (Local Foundation):** Lock down the native Linux host environment, map file paths, and verify hardware GPU acceleration drivers.
* **Phase 2 (Pipeline Compilation):** Link the approved Insta360 shared object binaries, verify headless C++ stitching output, and chain the core tools together using a master orchestration script.
* **Phase 3 (Algorithmic Tuning):** Analyze real telemetry data structures from your sessions to fine-tune the threshold parameters for what constitutes a highlight spike.
* **Phase 4 (Cloud Architecture):** Containerize the verified pipeline into a Docker sandbox to prepare for remote upload pipelines, moving compute limits away from local setups.

---

## Current State

* **Hardware:** The custom mechanical mount is fully engineered, manufactured, and field-tested under real conditions.
* **Software Gate:** The automated processing architecture has been mapped out.
* **Dependencies:** The official Insta360 Desktop Media SDK has been provided. API documentation and reference samples are hosted at the [Insta360Develop GitHub Organization](https://github.com/Insta360Develop/).
* **Target OS:** System deployment target is confirmed as a native Ubuntu 22.04 LTS server environment running on an x86_64 computing architecture.

---

## Next Steps

1. Execute the workspace setup script provided below to build your physical workspace footprint.
2. Place the official header files in `thirdParty/insta360Sdk/include/` and the shared libraries (`libMediaSDK.so`, etc.) in `thirdParty/insta360Sdk/lib/`.
3. Verify that your host computer has vendor-specific graphics drivers configured to handle heavy parallel execution loops.

---

## Project Folder Structure

```text
kitefoilPipeline/
├── CMakeLists.txt              # Build configuration file
├── main.cpp                    # C++ Headless SDK stitcher application
├── extractHighlights.py        # Python telemetry parsing and FFmpeg slicing script
├── runPipeline.sh              # Master orchestration supervisor script
├── build/                      # Compilation binaries output path
├── rawIngest/                  # Drop zone for raw unstitched file blocks
├── processScratch/             # High speed working directory for massive master files
├── outputHighlights/           # Destination folder for finalized action clips
└── thirdParty/
    └── insta360Sdk/
        ├── include/            # C++ header files compiled from GitHub
        └── lib/                # Shared object binaries downloaded from developer dashboard