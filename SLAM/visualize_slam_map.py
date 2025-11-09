#!/usr/bin/env python3
"""
Enhanced SLAM Map Visualizer

Visualizes saved SLAM maps with trajectory, statistics, and interactive controls.

Features:
- Point cloud map rendering with customizable colors
- Trajectory visualization with time-based coloring
- Start/end pose markers with coordinate frames
- Map statistics display
- Interactive camera controls
- Multiple viewing presets

Usage:
    # Visualize latest map
    python3 visualize_slam_map.py

    # Visualize specific session
    python3 visualize_slam_map.py --session 20251106_185550

    # With custom voxel downsampling
    python3 visualize_slam_map.py --voxel 0.1

    # Custom map and trajectory files
    python3 visualize_slam_map.py --map path/to/map.pcd --traj path/to/trajectory.csv
"""

import argparse
import json
import numpy as np
import open3d as o3d
from pathlib import Path
from datetime import datetime


class SlamMapVisualizer:
    """Enhanced visualizer for SLAM maps and trajectories"""

    def __init__(self, map_path=None, traj_path=None, meta_path=None, voxel_size=0.0):
        """
        Initialize visualizer

        Args:
            map_path: Path to .pcd map file
            traj_path: Path to .csv trajectory file (TUM format)
            meta_path: Path to run_meta.json file (optional)
            voxel_size: Voxel downsampling size (0 = no downsampling)
        """
        self.map_path = map_path
        self.traj_path = traj_path
        self.meta_path = meta_path
        self.voxel_size = voxel_size

        self.map_pcd = None
        self.poses = []
        self.metadata = None

    def load_data(self):
        """Load map, trajectory, and metadata"""
        print("=" * 70)
        print("SLAM Map Visualizer")
        print("=" * 70)

        # Load metadata if available
        if self.meta_path and Path(self.meta_path).exists():
            with open(self.meta_path, 'r') as f:
                self.metadata = json.load(f)
            self._print_metadata()

        # Load point cloud map
        if self.map_path and Path(self.map_path).exists():
            print(f"\nLoading map: {self.map_path}")
            self.map_pcd = o3d.io.read_point_cloud(str(self.map_path))

            original_points = len(self.map_pcd.points)
            print(f"  Original points: {original_points:,}")

            # Downsample if requested
            if self.voxel_size > 0:
                print(f"  Downsampling with voxel size: {self.voxel_size}m")
                self.map_pcd = self.map_pcd.voxel_down_sample(voxel_size=self.voxel_size)
                downsampled_points = len(self.map_pcd.points)
                ratio = downsampled_points / original_points * 100
                print(f"  Downsampled points: {downsampled_points:,} ({ratio:.1f}%)")

            # Color by height (same as viewer_realtime.py)
            self._colorize_by_height()
        else:
            print(f"\nWarning: Map file not found: {self.map_path}")

        # Load trajectory
        if self.traj_path and Path(self.traj_path).exists():
            print(f"\nLoading trajectory: {self.traj_path}")
            self.poses = self._load_trajectory(self.traj_path)
            print(f"  Poses loaded: {len(self.poses):,}")

            if self.poses:
                distance = self._calculate_trajectory_distance()
                print(f"  Total distance: {distance:.2f}m")
        else:
            print(f"\nWarning: Trajectory file not found: {self.traj_path}")

    def _load_trajectory(self, csv_path):
        """Load trajectory from TUM format CSV"""
        arr = np.loadtxt(csv_path, dtype=np.float64)
        if arr.ndim == 1:
            arr = arr[None, :]

        poses = []
        for row in arr:
            t, tx, ty, tz, qx, qy, qz, qw = row
            R = self._quat_to_rot(qx, qy, qz, qw)
            T = np.eye(4)
            T[:3, :3] = R
            T[:3, 3] = [tx, ty, tz]
            poses.append(T)

        return poses

    @staticmethod
    def _quat_to_rot(qx, qy, qz, qw):
        """Convert quaternion to rotation matrix"""
        x, y, z, w = qx, qy, qz, qw
        return np.array([
            [1-2*(y*y+z*z),   2*(x*y - z*w),   2*(x*z + y*w)],
            [  2*(x*y + z*w), 1-2*(x*x+z*z),   2*(y*z - x*w)],
            [  2*(x*z - y*w),   2*(y*z + x*w), 1-2*(x*x+y*y)]
        ], dtype=np.float64)

    def _calculate_trajectory_distance(self):
        """Calculate total trajectory distance"""
        if len(self.poses) < 2:
            return 0.0

        positions = np.array([T[:3, 3] for T in self.poses])
        deltas = np.diff(positions, axis=0)
        distances = np.linalg.norm(deltas, axis=1)
        return np.sum(distances)

    def _colorize_by_height(self):
        """Color points by Z height (blue=low, green=mid, red=high) - same as viewer_realtime.py"""
        if self.map_pcd is None or len(self.map_pcd.points) == 0:
            return

        pts = np.asarray(self.map_pcd.points)
        z = pts[:, 2]
        z_min = max(z.min(), -2.0)
        z_max = min(z.max(), 2.0)

        # Normalize to [0, 1]
        norm = np.clip((z - z_min) / max(z_max - z_min, 0.01), 0, 1)

        # Blue -> Green -> Red gradient
        colors = np.zeros((len(pts), 3))
        colors[:, 0] = norm                           # Red
        colors[:, 1] = 1.0 - np.abs(norm - 0.5) * 2  # Green (peak at 0.5)
        colors[:, 2] = 1.0 - norm                     # Blue

        self.map_pcd.colors = o3d.utility.Vector3dVector(colors)

    def _print_metadata(self):
        """Print metadata information"""
        print("\nSession Information:")
        print(f"  Timestamp: {self.metadata.get('timestamp', 'N/A')}")
        print(f"  Frames: {self.metadata.get('frames', 'N/A'):,}")
        print(f"  Total Points: {self.metadata.get('points', 'N/A'):,}")
        print(f"  Distance: {self.metadata.get('distance_m', 0):.2f}m")

        if 'args' in self.metadata:
            args = self.metadata['args']
            print(f"\nConfiguration:")
            print(f"  Frame rate: {args.get('frame_rate', 'N/A')} Hz")
            print(f"  Range: {args.get('min_range', 'N/A')} - {args.get('max_range', 'N/A')}m")
            print(f"  Voxel size: {args.get('voxel_size', 'N/A')}m")
            print(f"  Preset: {args.get('preset', 'N/A')}")

    def _create_coordinate_frame(self, pose, size=0.3):
        """Create a coordinate frame at given pose"""
        frame = o3d.geometry.TriangleMesh.create_coordinate_frame(size=size)
        frame.transform(pose)
        return frame

    def _create_trajectory_lines(self):
        """Create colored line set for trajectory - green like viewer_realtime.py"""
        if len(self.poses) < 2:
            return None

        # Extract positions
        positions = np.array([T[:3, 3] for T in self.poses], dtype=np.float64)

        # Create line indices
        lines = [[i, i+1] for i in range(len(positions)-1)]

        # Green color for all trajectory lines (same as viewer_realtime.py)
        colors = np.tile([0, 1, 0], (len(lines), 1))  # Green

        # Create line set
        line_set = o3d.geometry.LineSet(
            points=o3d.utility.Vector3dVector(positions),
            lines=o3d.utility.Vector2iVector(lines)
        )
        line_set.colors = o3d.utility.Vector3dVector(colors)

        return line_set

    def _create_pose_spheres(self, stride=100):
        """Create small spheres at pose locations"""
        if not self.poses:
            return []

        spheres = []
        for i in range(0, len(self.poses), stride):
            pos = self.poses[i][:3, 3]
            sphere = o3d.geometry.TriangleMesh.create_sphere(radius=0.05)
            sphere.translate(pos)

            # Color based on position in trajectory
            ratio = i / max(1, len(self.poses)-1)
            sphere.paint_uniform_color([ratio, 0.2, 1-ratio])
            spheres.append(sphere)

        return spheres

    def visualize(self, show_frames=True, show_spheres=False, sphere_stride=100):
        """
        Visualize the map and trajectory

        Args:
            show_frames: Show coordinate frames at start/end
            show_spheres: Show spheres along trajectory
            sphere_stride: Stride for sphere placement
        """
        geometries = []

        # Add point cloud map
        if self.map_pcd is not None:
            geometries.append(self.map_pcd)

        # Add trajectory line
        if self.poses:
            traj_lines = self._create_trajectory_lines()
            if traj_lines is not None:
                geometries.append(traj_lines)

            # Add start/end frames
            if show_frames and len(self.poses) > 0:
                # Start frame (larger, green-tinted)
                start_frame = self._create_coordinate_frame(self.poses[0], size=0.5)
                geometries.append(start_frame)

                # End frame (larger, red-tinted)
                end_frame = self._create_coordinate_frame(self.poses[-1], size=0.5)
                geometries.append(end_frame)

            # Add pose spheres
            if show_spheres:
                spheres = self._create_pose_spheres(stride=sphere_stride)
                geometries.extend(spheres)

        if not geometries:
            print("\nError: No geometries to visualize!")
            return

        # Print controls
        print("\n" + "=" * 70)
        print("Visualization Controls:")
        print("=" * 70)
        print("  Mouse:")
        print("    Left button + drag:              Rotate view")
        print("    Ctrl + Left button + drag:       Pan view")
        print("    Middle button (wheel) + drag:    Pan view")
        print("    Scroll wheel:                    Zoom in/out")
        print("    Shift + Left button + drag:      Roll view")
        print("  Keyboard:")
        print("    -/+:  Decrease/Increase point size")
        print("    R:    Reset view")
        print("    Q:    Quit")
        print("=" * 70)
        print("\nRendering... (Close window to exit)")

        # Create visualizer with same style as viewer_realtime.py
        vis = o3d.visualization.Visualizer()
        vis.create_window(
            window_name="G1 SLAM Map Viewer",
            width=1600,
            height=1000,
            left=50,
            top=50
        )

        # Add geometries
        for geom in geometries:
            vis.add_geometry(geom)

        # Set render options (match viewer_realtime.py)
        render_option = vis.get_render_option()
        render_option.background_color = np.array([0.1, 0.1, 0.15])  # Dark gray background
        render_option.point_size = 2.0  # Same point size as viewer_realtime
        render_option.show_coordinate_frame = True

        # Reset view to fit all geometries
        vis.reset_view_point(True)

        # Update once to initialize view
        vis.poll_events()
        vis.update_renderer()

        # Run visualizer with proper mouse controls
        vis.run()
        vis.destroy_window()


def find_latest_session(maps_dir):
    """Find the latest session directory"""
    maps_path = Path(maps_dir)

    # Check if 'latest' symlink exists
    latest_link = maps_path / 'latest'
    if latest_link.exists() and latest_link.is_symlink():
        return latest_link.resolve()

    # Find most recent directory by name
    session_dirs = [d for d in maps_path.iterdir() if d.is_dir() and d.name.startswith('202')]
    if session_dirs:
        return max(session_dirs, key=lambda d: d.name)

    return None


def main():
    parser = argparse.ArgumentParser(
        description="Visualize SLAM map and trajectory",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Visualize latest session
  python3 visualize_slam_map.py

  # Visualize specific session
  python3 visualize_slam_map.py --session 20251106_185550

  # With downsampling
  python3 visualize_slam_map.py --voxel 0.1

  # Custom files
  python3 visualize_slam_map.py --map map.pcd --traj trajectory.csv
        """
    )

    parser.add_argument('--session', type=str,
                        help='Session directory name (e.g., 20251106_185550)')
    parser.add_argument('--map', type=str,
                        help='Path to map.pcd file')
    parser.add_argument('--traj', type=str,
                        help='Path to trajectory.csv file')
    parser.add_argument('--meta', type=str,
                        help='Path to run_meta.json file')
    parser.add_argument('--voxel', type=float, default=0.0,
                        help='Voxel downsampling size in meters (0 = no downsampling)')
    parser.add_argument('--maps-dir', type=str,
                        default='/home/unitree/AIM-Robotics/SLAM/maps',
                        help='Base maps directory')
    parser.add_argument('--no-frames', action='store_true',
                        help='Do not show coordinate frames at start/end')
    parser.add_argument('--show-spheres', action='store_true',
                        help='Show spheres along trajectory')
    parser.add_argument('--sphere-stride', type=int, default=100,
                        help='Stride for sphere placement along trajectory')

    args = parser.parse_args()

    # Determine paths
    if args.map and args.traj:
        # Use custom paths
        map_path = args.map
        traj_path = args.traj
        meta_path = args.meta
    else:
        # Use session directory
        maps_dir = Path(args.maps_dir)

        if args.session:
            session_dir = maps_dir / args.session
        else:
            session_dir = find_latest_session(maps_dir)

        if not session_dir or not session_dir.exists():
            print(f"Error: Session directory not found: {session_dir}")
            return 1

        map_path = session_dir / 'map.pcd'
        traj_path = session_dir / 'trajectory.csv'
        meta_path = session_dir / 'run_meta.json'

    # Create visualizer
    visualizer = SlamMapVisualizer(
        map_path=map_path,
        traj_path=traj_path,
        meta_path=meta_path,
        voxel_size=args.voxel
    )

    # Load data
    visualizer.load_data()

    # Visualize
    visualizer.visualize(
        show_frames=not args.no_frames,
        show_spheres=args.show_spheres,
        sphere_stride=args.sphere_stride
    )

    return 0


if __name__ == '__main__':
    exit(main())
