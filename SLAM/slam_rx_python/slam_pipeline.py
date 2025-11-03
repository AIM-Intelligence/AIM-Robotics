"""
SLAM Pipeline - KISS-ICP Wrapper

Wraps KISS-ICP odometry with filtering, coordinate transforms, and statistics.
"""

import numpy as np
from typing import Dict, Optional
from kiss_icp.kiss_icp import KissICP
from kiss_icp.config import KISSConfig
from frame_builder import Frame


class SlamStats:
    """SLAM processing statistics"""

    def __init__(self):
        self.frames_processed = 0
        self.frames_skipped = 0  # Low point count
        self.total_points_processed = 0
        self.distance_traveled = 0.0
        self.last_pose = np.eye(4)  # 4x4 identity
        self.map_points = None  # (Nm, 3) array

    def reset(self):
        """Reset all stats"""
        self.__init__()

    def __repr__(self):
        return (f"SlamStats(frames={self.frames_processed}, skipped={self.frames_skipped}, "
                f"pts={self.total_points_processed}, dist={self.distance_traveled:.2f}m)")


class SlamPipeline:
    """KISS-ICP wrapper with filtering and transforms"""

    # Mount correction matrix (sensor upside-down on G1)
    # Applied to SLAM OUTPUT (map + pose), not input
    # 4x4 homogeneous matrix for upside-down mount (180° flip about X-axis)
    _R_MOUNT = np.array([
        [ 1,  0,  0,  0],
        [ 0, -1,  0,  0],  # Flip Y
        [ 0,  0, -1,  0],  # Flip Z
        [ 0,  0,  0,  1]
    ], dtype=np.float64)

    def __init__(self,
                 max_range: float = 20.0,
                 min_range: float = 0.1,
                 voxel_size: float = 1.0,
                 self_filter_radius: float = 0.30,
                 self_filter_z: float = 0.24,
                 min_points_per_frame: int = 800,
                 preset: str = "indoor",
                 stats: Optional[SlamStats] = None):
        """
        Initialize SLAM pipeline

        Args:
            max_range: Maximum range filter (meters)
            min_range: Minimum range filter (meters)
            voxel_size: Voxel downsampling size (meters)
            self_filter_radius: Robot self-filter XY radius (meters)
            self_filter_z: Robot self-filter Z half-height (meters, symmetric ±)
            min_points_per_frame: Skip frames with fewer points (stability)
            preset: Configuration preset ("indoor" or "outdoor")
            stats: Statistics object (creates new if None)
        """
        self.max_range = max_range
        self.min_range = min_range
        self.voxel_size = voxel_size
        self.self_filter_radius = self_filter_radius
        self.self_filter_z = self_filter_z
        self.min_points_per_frame = min_points_per_frame
        self.preset = preset
        self.stats = stats if stats is not None else SlamStats()

        # Initialize KISS-ICP
        self._init_kiss_icp()

        # Pose tracking
        self.last_position = np.zeros(3)  # For distance calculation

    def _init_kiss_icp(self):
        """Initialize KISS-ICP odometry"""
        # Load default config
        config = KISSConfig()

        # Set required parameters (voxel_size must be set before creating KissICP)
        config.mapping.voxel_size = self.voxel_size
        config.data.max_range = self.max_range
        config.data.min_range = self.min_range

        # Apply preset adjustments (learned from unitree_g1_vibes)
        if self.preset == "indoor":
            config.data.max_range = min(self.max_range, 30.0)
            # ICP tuning for indoor (tighter convergence, more iterations)
            config.adaptive_threshold.min_motion_th = 0.03  # m
            config.registration.convergence_criterion = 5e-5
            config.registration.max_num_iterations = 800
            config.mapping.max_points_per_voxel = 50  # Increased for higher detail (was 30)
        elif self.preset == "outdoor":
            config.data.max_range = min(self.max_range, 120.0)
            # Larger voxels outdoors for better performance
            if self.voxel_size < 1.0:
                config.mapping.voxel_size = 1.0
            # ICP tuning for outdoor (looser convergence, fewer iterations)
            config.adaptive_threshold.min_motion_th = 0.10  # m
            config.registration.convergence_criterion = 1e-4
            config.registration.max_num_iterations = 500
            config.mapping.max_points_per_voxel = 30

        # Create KISS-ICP instance
        self.odometry = KissICP(config)

    def _filter_points(self, xyz: np.ndarray) -> np.ndarray:
        """
        Apply self-filtering (remove robot body points)

        Removes points within a cylinder around the sensor to filter out
        reflections from the robot's body (head/mounting). Uses symmetric
        Z-filtering (±z) which is more appropriate for cylindrical exclusion.

        Args:
            xyz: Input points (N, 3) in sensor frame

        Returns:
            Filtered points (M, 3)
        """
        if len(xyz) == 0:
            return xyz

        # Self-filter: remove points within cylinder around robot
        # XY plane distance from sensor centerline
        xy_dist = np.linalg.norm(xyz[:, :2], axis=1)
        close = xy_dist < self.self_filter_radius

        # Z-axis proximity (symmetric around sensor plane)
        near_plane = np.abs(xyz[:, 2]) < self.self_filter_z

        # Keep points that are NOT both close AND near plane
        mask = ~(close & near_plane)

        return xyz[mask]


    def register_frame(self, frame: Frame, debug: bool = False) -> Optional[Dict]:
        """
        Register a frame with KISS-ICP

        CRITICAL: Points are fed to SLAM in SENSOR FRAME (no transform applied).
        Mount correction is applied to SLAM OUTPUT (map + pose), not input.
        This is the correct approach per unitree_g1_vibes implementation.

        Args:
            frame: Point cloud frame
            debug: Enable debug logging

        Returns:
            Dictionary with SLAM results or None if frame skipped:
            {
                'pose': np.ndarray (4x4) - robot frame
                'num_points': int,
                'num_points_filtered': int,
                'distance_traveled': float,
                'frame_duration_s': float,
                'map_points': np.ndarray (Nm, 3) - robot frame
            }
        """
        # Check minimum points
        if frame.point_count < self.min_points_per_frame:
            self.stats.frames_skipped += 1
            if debug:
                print(f"[SLAM] ⊘ Frame skipped: {frame.point_count} < {self.min_points_per_frame} points")
            return None

        # Apply self-filter (in sensor frame)
        xyz_filtered = self._filter_points(frame.xyz)

        if len(xyz_filtered) < self.min_points_per_frame:
            self.stats.frames_skipped += 1
            if debug:
                print(f"[SLAM] ⊘ Frame skipped after filtering: {len(xyz_filtered)} < {self.min_points_per_frame}")
            return None

        # Create timestamp vector (linear interpolation over frame duration)
        duration_s = frame.duration_s()
        timestamps = np.linspace(0.0, duration_s, len(xyz_filtered), dtype=np.float64)

        # ========== CRITICAL: Feed SENSOR-FRAME points to SLAM ==========
        # KISS-ICP expects raw sensor coordinates. Mount correction is applied
        # to the OUTPUT (map + pose), not the input.
        self.odometry.register_frame(xyz_filtered, timestamps)

        if debug:
            print(f"[SLAM] Registered {len(xyz_filtered)} pts in sensor frame")
        # ================================================================

        # ========== Apply mount correction to SLAM OUTPUT ==========
        # Get pose in sensor frame
        pose_sensor = self.odometry.last_pose.copy()

        # Transform to robot frame (4x4 @ 4x4)
        pose_robot = self._R_MOUNT @ pose_sensor

        if debug:
            print(f"[SLAM] Pose transformed: sensor→robot frame")
        # ===========================================================

        # Update stats
        self.stats.frames_processed += 1
        self.stats.total_points_processed += len(xyz_filtered)
        self.stats.last_pose = pose_robot  # Store robot-frame pose

        # Calculate distance traveled
        current_position = pose_robot[:3, 3]
        delta_dist = np.linalg.norm(current_position - self.last_position)
        self.stats.distance_traveled += delta_dist
        self.last_position = current_position

        # Get map (KISS-ICP uses VoxelHashMap internally)
        # Store reference to map object
        if hasattr(self.odometry, 'local_map'):
            self.stats.map_points = self.odometry.local_map
        else:
            self.stats.map_points = None

        # For return value, extract and transform map points
        map_points = None
        if self.stats.map_points is not None and hasattr(self.stats.map_points, 'point_cloud'):
            try:
                # Extract map in sensor frame
                map_sensor = self.stats.map_points.point_cloud()
                # Transform to robot frame (N,3 @ 3x3.T)
                map_points = map_sensor @ self._R_MOUNT[:3, :3].T
            except Exception as e:
                if debug:
                    print(f"[SLAM] ⚠️  Failed to extract map: {e}")

        result = {
            'pose': pose_robot,
            'num_points': frame.point_count,
            'num_points_filtered': len(xyz_filtered),
            'distance_traveled': self.stats.distance_traveled,
            'frame_duration_s': duration_s,
            'map_points': map_points
        }

        if debug:
            pos = current_position
            print(f"[SLAM] ✓ Frame registered: pts={len(xyz_filtered)}, "
                  f"pos=[{pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f}], "
                  f"dist={self.stats.distance_traveled:.2f}m")
            # Additional map size debugging
            if map_points is not None:
                print(f"[SLAM]    Map size: {len(map_points)} points (robot frame)")

        return result

    def save_map(self, filename: str):
        """
        Save current map to PCD file (in robot frame)

        Args:
            filename: Output filename (.pcd)
        """
        import open3d as o3d

        if self.stats.map_points is None:
            print("[SLAM] No map to save")
            return

        # Extract points from VoxelHashMap
        try:
            # KISS-ICP VoxelHashMap has point_cloud() method
            if hasattr(self.stats.map_points, 'point_cloud'):
                map_sensor = self.stats.map_points.point_cloud()
            elif isinstance(self.stats.map_points, np.ndarray):
                map_sensor = self.stats.map_points
            else:
                print(f"[SLAM] Cannot extract points from map type: {type(self.stats.map_points)}")
                return

            if len(map_sensor) == 0:
                print("[SLAM] Map is empty")
                return

            # Transform from sensor frame to robot frame
            map_robot = map_sensor @ self._R_MOUNT[:3, :3].T

            # Create point cloud
            pcd = o3d.geometry.PointCloud()
            pcd.points = o3d.utility.Vector3dVector(map_robot)

            # Save
            o3d.io.write_point_cloud(filename, pcd)
            print(f"[SLAM] Map saved: {filename} ({len(map_robot)} points, robot frame)")

        except Exception as e:
            print(f"[SLAM] Failed to save map: {e}")


if __name__ == "__main__":
    # Quick self-test
    print("SLAM Pipeline Test")
    print("=" * 50)

    # Create pipeline
    pipeline = SlamPipeline(
        max_range=15.0,
        voxel_size=0.5,
        preset="indoor"
    )

    print(f"Initialized: {pipeline.stats}")

    # Simulate a frame
    from frame_builder import Frame

    # Generate random point cloud
    xyz = np.random.rand(5000, 3).astype(np.float32) * 10.0  # 5k points in 10m cube

    frame = Frame(
        xyz=xyz,
        start_ts_ns=1000000000,
        end_ts_ns=1050000000,  # 50ms duration
        seq_first=0,
        seq_last=10,
        pkt_count=10,
        point_count=5000
    )

    print(f"\nTest frame: {frame}")

    # Register
    result = pipeline.register_frame(frame, debug=True)

    if result:
        print(f"\nResult:")
        print(f"  Pose:\n{result['pose']}")
        print(f"  Points: {result['num_points']} → {result['num_points_filtered']} (filtered)")
        print(f"  Distance: {result['distance_traveled']:.2f}m")
        print(f"  Map points: {len(result['map_points'])}")

    print(f"\nFinal stats: {pipeline.stats}")
