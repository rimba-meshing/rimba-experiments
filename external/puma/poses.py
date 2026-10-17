"""Compensate the fixed KITTI transform in PUMA's GT pose loader."""
import numpy as np

PUMA_T_CAM_VELO = np.array(
    [
        [4.27680239e-04, -9.99967248e-01, -8.08449168e-03, -1.19845993e-02],
        [-7.21062651e-03, 8.08119847e-03, -9.99941316e-01, -5.40398473e-02],
        [9.99973865e-01, 4.85948581e-04, -7.20693369e-03, -2.92196865e-01],
        [0.0, 0.0, 0.0, 1.0],
    ],
    dtype=np.float64,
)

PUMA_T_VELO_CAM = np.array(
    [
        [4.27679428e-04, -7.21062673e-03, 9.99973959e-01, 2.91804720e-01],
        [-9.99967209e-01, 8.08119861e-03, 4.85949420e-04, -1.14055066e-02],
        [-8.08449174e-03, -9.99941381e-01, -7.20693461e-03, -5.6239412e-02],
        [0.0, 0.0, 0.0, 1.0],
    ],
    dtype=np.float64,
)


def prepare(source, output, frames, maicity):
    rows = np.loadtxt(source, dtype=np.float64).reshape((-1, 12))[:frames]
    poses = np.repeat(np.eye(4)[None], len(rows), axis=0)
    poses[:, :3, :4] = rows.reshape((-1, 3, 4))
    if maicity:
        poses = np.einsum("ij,njk,kl->nil", PUMA_T_CAM_VELO, poses, PUMA_T_VELO_CAM)
    np.savetxt(output, poses[:, :3, :4].reshape((-1, 12)), fmt="%.12g")
