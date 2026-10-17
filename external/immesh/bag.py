"""Write the sequence's original XYZI scans to an ImMesh ROS bag."""

import numpy as np
import rosbag
import rospy
from sensor_msgs.msg import PointCloud2, PointField

from external.common.case import load_case
from external.common.data import timestamps


def write(case):
    fields = [PointField(name, offset, PointField.FLOAT32, 1) for name, offset in (("x", 0), ("y", 4), ("z", 8), ("intensity", 12))]
    with rosbag.Bag(str(case.output / "input.bag"), "w") as bag:
        for index, seconds in enumerate(timestamps(case.workload)):
            points = np.fromfile(str(case.workload.directory / "velodyne" / f"{index:06d}.bin"), dtype=np.float32).reshape((-1, 4))
            message = PointCloud2()
            message.header.stamp = rospy.Time.from_sec(1600000000.0 + seconds)
            message.header.frame_id = "velodyne"
            message.height, message.width = 1, len(points)
            message.fields = fields
            message.is_bigendian, message.is_dense = False, False
            message.point_step, message.row_step = 16, 16 * len(points)
            message.data = points.tobytes()
            bag.write("/velodyne_points", message, message.header.stamp)


if __name__ == "__main__":
    write(load_case())
