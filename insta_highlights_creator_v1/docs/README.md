# Insta360 X5 Kitefoil Highlights Creator

Automatically stitches, stabilizes, and reframes raw dual-fisheye Insta360 footage to create locked-horizon action highlights.

---

## Gyroflow Telemetry Integration & Parameters

This pipeline utilizes [Gyroflow](https://gyroflow.xyz) to parse physical camera orientation metadata and apply hardware-stabilized telemetry coordinates to the rendering engine.

### 1. IMU Orientation Format (`imu_orientation`)
Inside the `.gyroflow` project file (under the `gyro_source` block), the IMU sensor mounting orientation relative to the camera lenses is described using a compact **XYZ string notation**:
*   **Axis Ordering**: The sequence of letters (e.g., `XYZ`, `YXZ`, `ZYX`) specifies how the IMU axes are mapped to the camera sensor coordinates.
*   **Axis Inversion**:
    *   **Uppercase (`X`, `Y`, `Z`)**: Indicates a positive axis direction.
    *   **Lowercase (`x`, `y`, `z`)**: Indicates an inverted (negative) axis direction.
*   **Example**: `'Xyz'` maps the IMU X-axis to the camera's forward axis, Y-axis to lateral (inverted), and Z-axis to vertical (inverted).

### 2. Synchronization & Project Schema
*   **`gyro_source`**: Houses parameters for `'imu_orientation'`, gyroscope bias corrections (`'gyro_bias'`), and low-pass filtering.
*   **`stabilization`**: Defines the target smoothing method (e.g., `'Default'`, `'LPF'`), horizon locking parameter `'horizon_lock_amount'` (ranging from `0.0` to `1.0`), and per-axis smoothing weights.
*   **`synchronization`**: Holds the initial time sync offset (`'initial_offset'`) in milliseconds between the video frames and physical IMU records.

---

## External References & Source Code

For the underlying implementations of Gyroflow's serialization formats and hardware parsers, refer to the official repositories:
*   **Gyroflow Core Engine**: [gyroflow/gyroflow](https://github.com/gyroflow/gyroflow) (the project structure serialization and stabilization calculations are located in `src/core/`).
*   **Telemetry Logging & Parser**: [gyroflow/telemetry-parser](https://github.com/gyroflow/telemetry-parser) (the low-level parser that reads embedded gyroscope and accelerometer records from `.insv` containers).

