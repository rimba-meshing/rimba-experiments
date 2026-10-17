#!/usr/bin/env python3
import argparse
import time
from pathlib import Path

import numpy as np
import rospy
from geometry_msgs.msg import Quaternion, TransformStamped
from nav_msgs.msg import Odometry
from sensor_msgs.msg import PointCloud2, PointField
from std_msgs.msg import Header
import tf.transformations as tft
from tf2_ros import TransformBroadcaster


def load_poses(path):
    rows = []
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        vals = [float(x) for x in line.split()]
        mat = np.eye(4, dtype=np.float64)
        mat[:3, :4] = np.asarray(vals, dtype=np.float64).reshape(3, 4)
        rows.append(mat)
    return np.stack(rows)


def load_times(path, n):
    p = Path(path)
    if not p.exists():
        return [i * 0.1 for i in range(n)]
    vals = [float(x.strip()) for x in p.read_text().splitlines() if x.strip()]
    if len(vals) < n:
        return [i * 0.1 for i in range(n)]
    return vals[:n]


def load_calib(path):
    tr = np.eye(4, dtype=np.float64)
    p = Path(path)
    if not p.exists():
        return tr
    for line in p.read_text().splitlines():
        if line.startswith("Tr:") or line.startswith("Tr_velo_to_cam:"):
            vals = [float(x) for x in line.split()[1:]]
            tr[:3, :4] = np.asarray(vals, dtype=np.float64).reshape(3, 4)
            return tr
    return tr


def pose_for_dataset(pose, tr, convert_camera_to_lidar):
    if not convert_camera_to_lidar:
        return pose
    return np.linalg.inv(tr) @ pose @ tr


def cloud_msg(points, stamp, frame_id):
    arr = np.asarray(points, dtype=np.float32)
    msg = PointCloud2()
    msg.header.stamp = stamp
    msg.header.frame_id = frame_id
    msg.height = 1
    msg.width = arr.shape[0]
    msg.fields = [
        PointField("x", 0, PointField.FLOAT32, 1),
        PointField("y", 4, PointField.FLOAT32, 1),
        PointField("z", 8, PointField.FLOAT32, 1),
        PointField("intensity", 12, PointField.FLOAT32, 1),
    ]
    msg.is_bigendian = False
    msg.point_step = 16
    msg.row_step = msg.point_step * msg.width
    msg.is_dense = True
    msg.data = arr.tobytes()
    return msg


def odom_msg(pose, stamp, frame_id, child_frame_id):
    quat = tft.quaternion_from_matrix(pose)
    msg = Odometry()
    msg.header.stamp = stamp
    msg.header.frame_id = frame_id
    msg.child_frame_id = child_frame_id
    msg.pose.pose.position.x = float(pose[0, 3])
    msg.pose.pose.position.y = float(pose[1, 3])
    msg.pose.pose.position.z = float(pose[2, 3])
    msg.pose.pose.orientation = Quaternion(float(quat[0]), float(quat[1]), float(quat[2]), float(quat[3]))
    return msg


def tf_msg(pose, stamp, frame_id, child_frame_id):
    quat = tft.quaternion_from_matrix(pose)
    msg = TransformStamped()
    msg.header.stamp = stamp
    msg.header.frame_id = frame_id
    msg.child_frame_id = child_frame_id
    msg.transform.translation.x = float(pose[0, 3])
    msg.transform.translation.y = float(pose[1, 3])
    msg.transform.translation.z = float(pose[2, 3])
    msg.transform.rotation = Quaternion(float(quat[0]), float(quat[1]), float(quat[2]), float(quat[3]))
    return msg


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--velodyne-dir", required=True)
    parser.add_argument("--poses", required=True)
    parser.add_argument("--times", required=True)
    parser.add_argument("--calib", required=True)
    parser.add_argument("--max-frames", type=int, required=True)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--rate", type=float, default=1.0)
    parser.add_argument("--replay-mode", choices=("ack", "rate"), default="ack")
    parser.add_argument("--ack-topic", default="/cad_mesher/scan_processed")
    parser.add_argument("--ack-timeout-seconds", type=float, default=60.0)
    parser.add_argument("--initial-settle-seconds", type=float, default=3.0)
    parser.add_argument("--frame-id", default="velodyne")
    parser.add_argument("--odom-frame", default="map")
    return parser.parse_args()


def main():
    args = parse_args()
    rospy.init_node("cad_mesher_dataset_replay", anonymous=True)
    cloud_pub = rospy.Publisher("/mapping_cloud", PointCloud2, queue_size=4)
    odom_pub = rospy.Publisher("/mapping_odom", Odometry, queue_size=4)
    tf_pub = TransformBroadcaster()
    latest_ack = {"stamp": float("-inf"), "count": 0}

    def ack_callback(message):
        stamp = message.stamp.to_sec()
        latest_ack["stamp"] = max(latest_ack["stamp"], stamp)
        latest_ack["count"] += 1

    if args.replay_mode == "ack":
        rospy.Subscriber(args.ack_topic, Header, ack_callback, queue_size=100)

    deadline = rospy.Time.now() + rospy.Duration(20.0)
    while not rospy.is_shutdown() and rospy.Time.now() < deadline:
        if cloud_pub.get_num_connections() > 0 and odom_pub.get_num_connections() > 0:
            break
        rospy.sleep(0.1)

    if cloud_pub.get_num_connections() == 0 or odom_pub.get_num_connections() == 0:
        raise RuntimeError("CAD-Mesher did not subscribe to the replay topics")
    scan_files = sorted(Path(args.velodyne_dir).glob("*.bin"))[: args.max_frames]
    poses = load_poses(args.poses)
    times = load_times(args.times, len(scan_files))
    tr = load_calib(args.calib)
    convert = args.dataset == "kitti_odom"
    rate = rospy.Rate(max(args.rate, 0.001))
    published = 0

    def wait_for_ack(target_stamp):
        deadline = time.monotonic() + args.ack_timeout_seconds
        while not rospy.is_shutdown():
            if latest_ack["stamp"] + 1e-6 >= target_stamp:
                return
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    f"timeout waiting for CAD acknowledgement at stamp {target_stamp}; "
                    f"last_ack={latest_ack['stamp']} count={latest_ack['count']}"
                )
            rospy.sleep(0.001)

    for i, scan in enumerate(scan_files):
        if rospy.is_shutdown():
            break
        pts = np.fromfile(str(scan), dtype=np.float32).reshape((-1, 4))
        pose = pose_for_dataset(poses[i], tr, convert)
        stamp = rospy.Time.from_sec(times[i])
        odom = odom_msg(pose, stamp, args.odom_frame, args.frame_id)
        cloud = cloud_msg(pts, stamp, args.frame_id)
        odom_pub.publish(odom)
        tf_pub.sendTransform(tf_msg(pose, stamp, args.odom_frame, args.frame_id))
        rospy.sleep(0.01)
        cloud_pub.publish(cloud)
        published += 1
        if args.replay_mode == "ack":
            if i == 0:
                # CAD-Mesher uses the first scan to initialize the global map
                # and does not emit the per-update acknowledgement for it.
                rospy.sleep(args.initial_settle_seconds)
            else:
                wait_for_ack(times[i])
        else:
            rate.sleep()
    if published != args.max_frames:
        raise RuntimeError("Replay stopped before delivering the requested interval")
    print(
        f"published_frames={published} replay_mode={args.replay_mode} "
        f"ack_count={latest_ack['count']}",
        flush=True,
    )
    rospy.sleep(2.0)


if __name__ == "__main__":
    main()
