#!/usr/bin/env python3
"""
viz_map_traj.py — Offline viewer for G1 SLAM outputs (no v2 naming)
- Loads map (.pcd) and trajectory (.csv, TUM: t tx ty tz qx qy qz qw)
- Renders with Open3D: map points, trajectory polyline, start/end axes

Usage:
  python3 viz_map_traj.py --map map.pcd --traj trajectory.csv
  python3 viz_map_traj.py --map /path/to/map.pcd --traj /path/to/trajectory.csv --voxel 0.1
"""
import argparse
import numpy as np
import open3d as o3d

def axis(T, size=0.3):
    frame = o3d.geometry.TriangleMesh.create_coordinate_frame(size=size)
    frame.transform(T)
    return frame

def quat_to_rot(qx, qy, qz, qw):
    x, y, z, w = qx, qy, qz, qw
    return np.array([
        [1-2*(y*y+z*z),   2*(x*y - z*w),   2*(x*z + y*w)],
        [  2*(x*y + z*w), 1-2*(x*x+z*z),   2*(y*z - x*w)],
        [  2*(x*z - y*w),   2*(y*z + x*w), 1-2*(x*x+y*y)]
    ], dtype=np.float64)

def tum_to_poses(csv_path):
    arr = np.loadtxt(csv_path, dtype=np.float64)
    if arr.ndim == 1:
        arr = arr[None, :]
    poses = []
    for t, tx, ty, tz, qx, qy, qz, qw in arr.tolist():
        R = quat_to_rot(qx, qy, qz, qw)
        T = np.eye(4); T[:3,:3] = R; T[:3,3] = [tx, ty, tz]
        poses.append(T)
    return poses

def build_traj_lines(poses):
    if len(poses) < 2:
        return None
    pts = np.array([T[:3,3] for T in poses], dtype=np.float64)
    lines = [[i, i+1] for i in range(len(pts)-1)]
    colors = np.zeros((len(lines), 3))
    for i in range(len(lines)):
        c = i / max(1, len(lines)-1)  # blue -> red
        colors[i] = [c, 0.2, 1.0 - c]
    ls = o3d.geometry.LineSet(
        points=o3d.utility.Vector3dVector(pts),
        lines=o3d.utility.Vector2iVector(lines)
    )
    ls.colors = o3d.utility.Vector3dVector(colors)
    return ls

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", type=str, required=False, help="PCD map file")
    ap.add_argument("--traj", type=str, required=False, help="Trajectory CSV (TUM format)")
    ap.add_argument("--voxel", type=float, default=0.0, help="Optional voxel downsample size (m)")
    args = ap.parse_args()

    geoms = []

    if args.map:
        pcd = o3d.io.read_point_cloud(args.map)
        if args.voxel and args.voxel > 0:
            pcd = pcd.voxel_down_sample(voxel_size=args.voxel)
        pcd.paint_uniform_color([0.8, 0.8, 0.8])
        geoms.append(pcd)

    poses = []
    if args.traj:
        poses = tum_to_poses(args.traj)
        traj = build_traj_lines(poses)
        if traj:
            geoms.append(traj)
        if poses:
            geoms.append(axis(poses[0], size=0.35))   # start
            geoms.append(axis(poses[-1], size=0.35))  # end

    if not geoms:
        print("Nothing to show. Provide --map and/or --traj.")
        return

    print("→ Rendering... (Open3D)")
    o3d.visualization.draw_geometries(
        geoms,
        window_name="G1 SLAM — Map & Trajectory",
        width=1280, height=800
    )

    if poses:
        P = np.asarray([T[:3,3] for T in poses])
        d = np.linalg.norm(np.diff(P, axis=0), axis=1) if len(P) > 1 else np.array([0.0])
        print(f"Trajectory: {len(poses)} poses, distance={d.sum():.2f} m")

if __name__ == "__main__":
    main()
