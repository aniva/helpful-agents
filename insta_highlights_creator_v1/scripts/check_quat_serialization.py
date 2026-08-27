import json
from scipy.spatial.transform import Rotation as R
import numpy as np

def main():
    camera_json_path = "/mnt/c/Users/me/.gemini/antigravity/scratch/camera.json"
    with open(camera_json_path, "r") as f:
        metadata = json.load(f)
        
    m = metadata[0]
    org_quat = m['org_quat'] # [w, x, y, z] in Gyroflow
    org_euler = m['org_euler'] # [roll, pitch, yaw] or [pitch, roll, yaw]?
    
    # SciPy uses [x, y, z, w]
    q_scipy = [org_quat[1], org_quat[2], org_quat[3], org_quat[0]]
    rot = R.from_quat(q_scipy)
    
    print(f"Gyroflow org_euler: {org_euler}")
    
    orders = [
        'xyz', 'xzy', 'yxz', 'yzx', 'zxy', 'zyx',
        'XYZ', 'XZY', 'YXZ', 'YZX', 'ZXY', 'ZYX'
    ]
    
    for order in orders:
        euler_deg = rot.as_euler(order, degrees=True)
        print(f"Order {order}: {euler_deg}")

if __name__ == "__main__":
    main()
