import numpy as np
from scipy.spatial.transform import Rotation as R

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

def main():
    q_gyro = [0.6359497517576336, -0.5800024537962237, 0.47817357982228237, 0.17468570094134778] # [w, x, y, z]
    q_scipy = [q_gyro[1], q_gyro[2], q_gyro[3], q_gyro[0]] # [x, y, z, w]
    
    R_custom = quat_to_matrix(q_gyro)
    R_scipy = R.from_quat(q_scipy).as_matrix()
    
    print("R_custom:")
    print(R_custom)
    print("R_scipy:")
    print(R_scipy)
    print("Diff norm:", np.linalg.norm(R_custom - R_scipy))
    print("Diff transposed norm:", np.linalg.norm(R_custom.T - R_scipy))

if __name__ == "__main__":
    main()
