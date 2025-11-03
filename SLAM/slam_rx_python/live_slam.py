#!/usr/bin/env python3
"""
G1 Live SLAM - LiDAR Stream Receiver & SLAM Pipeline

Receives LiDAR packets from lidar_stream transmitter,
builds frames, and processes with KISS-ICP SLAM.

Usage:
    python3 live_slam.py [options]

Examples:
    # Indoor SLAM (20Hz, default settings)
    python3 live_slam.py --frame-rate 20

    # Outdoor SLAM (10Hz, longer range)
    python3 live_slam.py --frame-rate 10 --max-range 50 --preset outdoor

    # Debug mode
    python3 live_slam.py --frame-rate 20 --debug
"""

import socket
import argparse
import signal
import sys
import time
import math
import struct
from pathlib import Path
import json
import numpy as np
from datetime import datetime

try:
    import zmq
    ZMQ_AVAILABLE = True
except ImportError:
    ZMQ_AVAILABLE = False
    print("⚠ ZMQ not available. Install with: pip3 install pyzmq")

# Import our modules
from lidar_protocol import LidarProtocol, ProtocolStats
from frame_builder import FrameBuilder, FrameBuilderStats
from slam_pipeline import SlamPipeline, SlamStats


class LiveSlam:
    """Main SLAM application"""

    def __init__(self, args):
        self.args = args
        self.running = True

        # Statistics
        self.protocol_stats = ProtocolStats()
        self.frame_stats = FrameBuilderStats()
        self.slam_stats = SlamStats()

        # Components
        self.protocol = LidarProtocol(
            validate_crc=True,
            stats=self.protocol_stats
        )

        self.frame_builder = FrameBuilder(
            frame_period_s=1.0 / args.frame_rate,
            max_frame_points=120000,
            stats=self.frame_stats
        )

        self.slam_pipeline = SlamPipeline(
            max_range=args.max_range,
            min_range=args.min_range,
            voxel_size=args.voxel_size,
            self_filter_radius=args.self_filter_radius,
            self_filter_z=args.self_filter_z,
            min_points_per_frame=args.min_points_per_frame,
            preset=args.preset,
            stats=self.slam_stats
        )

        # UDP socket
        self.sock = None

        # Logging
        self.last_log_time = time.time()
        self.log_interval = 1.0  # seconds

        # Pose drift tracking (for stationary test)
        self.pose_history = []

        # Trajectory: list of (t[sec], 4x4 pose)
        self.traj_records = []
        self.start_wall_time = time.time()

        # ZMQ Streaming
        self.stream_enabled = args.stream_enable and ZMQ_AVAILABLE
        self.stream_port = args.stream_port
        self.stream_voxel = args.stream_voxel
        self.stream_max_points = args.stream_max_points
        self.frame_id = 0
        self.frame_count = 0  # Frame counter for streaming
        self.zctx = None
        self.pub = None

        # ========== Warmup for SLAM initialization ==========
        # DISABLED - Not needed with proper coordinate transform
        self.warmup_frames = 0
        self.warmup_needed = 0  # No warmup (was 10, but unitree_g1_vibes doesn't use warmup)
        # ====================================================

        if self.stream_enabled:
            self.zctx = zmq.Context.instance()
            self.pub = self.zctx.socket(zmq.PUB)
            self.pub.bind(f"tcp://0.0.0.0:{self.stream_port}")
            print(f"[STREAM] ZMQ PUB bound to tcp://0.0.0.0:{self.stream_port}")

    @staticmethod
    def _rot_to_quat(R: np.ndarray):
        """Rotation matrix(3x3) -> quaternion (qx, qy, qz, qw)"""
        m00, m01, m02 = R[0,0], R[0,1], R[0,2]
        m10, m11, m12 = R[1,0], R[1,1], R[1,2]
        m20, m21, m22 = R[2,0], R[2,1], R[2,2]
        tr = m00 + m11 + m22
        if tr > 0:
            S = math.sqrt(tr + 1.0) * 2
            qw = 0.25 * S
            qx = (m21 - m12) / S
            qy = (m02 - m20) / S
            qz = (m10 - m01) / S
        elif (m00 > m11) and (m00 > m22):
            S = math.sqrt(1.0 + m00 - m11 - m22) * 2
            qw = (m21 - m12) / S
            qx = 0.25 * S
            qy = (m01 + m10) / S
            qz = (m02 + m20) / S
        elif m11 > m22:
            S = math.sqrt(1.0 + m11 - m00 - m22) * 2
            qw = (m02 - m20) / S
            qx = (m01 + m10) / S
            qy = 0.25 * S
            qz = (m12 + m21) / S
        else:
            S = math.sqrt(1.0 + m22 - m00 - m11) * 2
            qw = (m10 - m01) / S
            qx = (m02 + m20) / S
            qy = (m12 + m21) / S
            qz = 0.25 * S
        return (qx, qy, qz, qw)

    def _save_trajectory(self, prefix: str):
        """Save trajectory to .csv (TUM) and .npy"""
        if not self.traj_records:
            print("[TRJ] No trajectory to save")
            return
        rows = []
        for t, pose in self.traj_records:
            R = pose[:3, :3]
            tx, ty, tz = pose[:3, 3]
            qx, qy, qz, qw = self._rot_to_quat(R)
            rows.append([t, tx, ty, tz, qx, qy, qz, qw])
        arr = np.asarray(rows, dtype=np.float64)
        csv_path = f"{prefix}.csv"
        npy_path = f"{prefix}.npy"
        np.savetxt(csv_path, arr, fmt="%.9f", delimiter=" ")
        np.save(npy_path, arr)
        print(f"[TRJ] Trajectory saved: {csv_path}  ({len(arr)} poses)")
        print(f"[TRJ] Numpy backup   : {npy_path}")

    def _ds_for_stream(self, xyz: np.ndarray) -> np.ndarray:
        """Downsample points for streaming"""
        pts = xyz
        # Simple cap - can add voxel downsampling if needed
        if len(pts) > self.stream_max_points:
            idx = np.linspace(0, len(pts)-1, self.stream_max_points, dtype=np.int32)
            pts = pts[idx]
        return pts.astype(np.float32, copy=False)

    def _get_map_points(self):
        """Extract current SLAM map points"""
        try:
            # Get map from KISS-ICP
            if hasattr(self.slam_pipeline.odometry, 'local_map'):
                local_map = self.slam_pipeline.odometry.local_map
                # VoxelHashMap has point_cloud() method
                if hasattr(local_map, 'point_cloud'):
                    pts = local_map.point_cloud()
                    # ========== DEBUG: Map size ==========
                    if self.args.debug and self.frame_count % 50 == 0:
                        print(f"🗺️  [MAP] Extracted {len(pts)} points from SLAM map")
                    # =====================================
                    return pts
            # ========== WARNING: No map found ==========
            if self.args.debug and self.frame_count % 50 == 0:
                print("⚠️  [MAP] No local_map attribute found!")
            # ===========================================
            return None
        except Exception as e:
            print(f"❌ [MAP] Failed to get map: {e}")  # Always print errors
            if self.args.debug:
                import traceback
                traceback.print_exc()
            return None

    def _send_frame(self, pose4x4: np.ndarray, t_sec: float):
        """Send frame via ZMQ (G1PC protocol) - sends SLAM MAP, not raw scan"""
        if not self.stream_enabled:
            return

        try:
            # Get current SLAM map points (world coordinates)
            map_pts = self._get_map_points()
            if map_pts is None or len(map_pts) == 0:
                # ========== WARNING: Empty map ==========
                if self.args.debug and self.slam_stats.frames_processed % 50 == 0:
                    print(f"⚠️  [STREAM] Empty map at frame #{self.slam_stats.frames_processed}")
                # ========================================
                return

            # Downsample map for streaming
            pts = self._ds_for_stream(map_pts)

            # ========== DEBUG: Streaming confirmation ==========
            if self.args.debug and self.slam_stats.frames_processed % 50 == 0:
                print(f"📡 [STREAM] Sending {len(pts)} points (frame #{self.slam_stats.frames_processed})")
            # ===================================================

            magic = b'G1PC'
            version = 1
            frame_id = self.frame_id
            self.frame_id += 1
            pose = pose4x4.astype(np.float32).reshape(-1)
            count = np.uint32(len(pts))

            # Header: '<4sBId16fI'
            header = struct.pack('<4sBId16fI',
                                magic, version, frame_id, float(t_sec),
                                *pose, int(count))

            # Send header + payload
            self.pub.send(header + pts.tobytes(order='C'), zmq.NOBLOCK)
        except Exception as e:
            if self.args.debug:
                print(f"[STREAM] Send error: {e}")

    def setup_socket(self):
        """Create and configure UDP socket"""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((self.args.listen_ip, self.args.listen_port))
        self.sock.settimeout(0.1)  # 100ms timeout for clean shutdown

        print(f"✓ UDP socket listening on {self.args.listen_ip}:{self.args.listen_port}")

    def signal_handler(self, signum, frame):
        """Handle Ctrl+C gracefully"""
        print("\n\n⚠ Shutdown signal received...")
        self.running = False

    def log_stats(self, force=False):
        """Print periodic statistics"""
        now = time.time()
        if not force and (now - self.last_log_time) < self.log_interval:
            return

        elapsed = now - self.last_log_time
        self.last_log_time = now

        # Calculate rates
        pps = self.protocol_stats.total_packets / max(elapsed, 0.001)

        # Protocol stats
        print(f"\n{'='*70}")
        print(f"[RX] Packets: {self.protocol_stats.total_packets} "
              f"({pps:.1f} pps), Valid: {self.protocol_stats.valid_packets}")
        print(f"     Errors: CRC={self.protocol_stats.crc_failures}, "
              f"Magic={self.protocol_stats.bad_magic}, "
              f"Len={self.protocol_stats.len_mismatch}")

        # Frame stats
        avg_pts_per_frame = (self.frame_stats.points_added / max(self.frame_stats.frames_built, 1))
        print(f"[FRAME] Built: {self.frame_stats.frames_built}, "
              f"Packets: {self.frame_stats.packets_added}, "
              f"Avg pts/frame: {avg_pts_per_frame:.0f}")
        print(f"        Late: {self.frame_stats.late_packets}, "
              f"Gaps: {self.frame_stats.seq_gaps}, "
              f"Reorder: {self.frame_stats.seq_reorders}")

        # SLAM stats
        if self.slam_stats.frames_processed > 0:
            pos = self.slam_stats.last_pose[:3, 3]
            print(f"[SLAM] Processed: {self.slam_stats.frames_processed}, "
                  f"Skipped: {self.slam_stats.frames_skipped}")
            print(f"       Position: [{pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f}], "
                  f"Distance: {self.slam_stats.distance_traveled:.2f}m")
            # Note: map_points is VoxelHashMap, not array
            if self.slam_stats.map_points is not None:
                try:
                    # Try to get point count if available
                    if isinstance(self.slam_stats.map_points, np.ndarray):
                        print(f"       Map points: {len(self.slam_stats.map_points)}")
                    else:
                        print(f"       Map: active (VoxelHashMap)")
                except:
                    pass

        print(f"{'='*70}")

    def analyze_pose_drift(self):
        """Analyze pose stability (for stationary test)"""
        if len(self.pose_history) < 2:
            return

        positions = np.array([p[:3, 3] for p in self.pose_history])
        deltas = np.diff(positions, axis=0)
        distances = np.linalg.norm(deltas, axis=1)

        mean_drift = np.mean(distances)
        std_drift = np.std(distances)
        max_drift = np.max(distances)

        print(f"\n{'='*70}")
        print(f"POSE DRIFT ANALYSIS ({len(self.pose_history)} samples)")
        print(f"{'='*70}")
        print(f"Mean Δt per frame: {mean_drift:.4f} m")
        print(f"Std deviation:     {std_drift:.4f} m")
        print(f"Max Δt:            {max_drift:.4f} m")

        # Acceptance criterion
        if mean_drift < 0.02:
            print(f"✅ PASS: Mean drift < 0.02m (stationary stability)")
        else:
            print(f"⚠️  WARN: Mean drift = {mean_drift:.4f}m (> 0.02m threshold)")

        print(f"{'='*70}\n")

    def run(self):
        """Main processing loop"""
        print("\n" + "="*70)
        print("G1 Live SLAM ")
        print("="*70)
        print(f"Frame rate:       {self.args.frame_rate} Hz")
        print(f"Range:            {self.args.min_range} - {self.args.max_range} m")
        print(f"Voxel size:       {self.args.voxel_size} m")
        print(f"Self-filter:      r={self.args.self_filter_radius}m, z=±{self.args.self_filter_z}m (symmetric)")
        print(f"Min pts/frame:    {self.args.min_points_per_frame}")
        print(f"Preset:           {self.args.preset} (ICP tuning applied)")
        print(f"Debug:            {self.args.debug}")
        print("="*70 + "\n")

        print("✓ SLAM coordinate fix applied (sensor frame → SLAM → robot frame transform)")
        print("✓ ICP parameters tuned for indoor/outdoor presets")
        print("✓ Symmetric Z-axis self-filtering enabled")
        print("✓ High-detail mapping (voxel=0.2m, 50 pts/voxel)")
        print()

        # Setup
        self.setup_socket()

        # Signal handler
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

        print("Listening for LiDAR packets... (Ctrl+C to stop)\n")

        try:
            while self.running:
                try:
                    # Receive UDP packet
                    data, addr = self.sock.recvfrom(2048)

                    # Parse packet
                    packet = self.protocol.parse_datagram(data, debug=self.args.debug)

                    if packet is None:
                        continue  # Invalid packet

                    # Add to frame builder
                    frame = self.frame_builder.add_packet(
                        device_ts_ns=packet['device_ts_ns'],
                        points_xyz=packet['xyz'],
                        seq=packet['seq'],
                        debug=self.args.debug
                    )

                    # Process complete frame
                    if frame is not None:
                        # ========== WARMUP: Skip first N frames ==========
                        if self.warmup_frames < self.warmup_needed:
                            self.warmup_frames += 1
                            if self.warmup_frames == 1:
                                print(f"⏳ [WARMUP] Discarding first {self.warmup_needed} frames for SLAM initialization...")
                            continue
                        # =================================================

                        result = self.slam_pipeline.register_frame(frame, debug=self.args.debug)

                        if result is not None:
                            # Increment frame counter for streaming
                            self.frame_count += 1
                            # Track pose for drift analysis
                            self.pose_history.append(result['pose'].copy())
                            # Trajectory record (wall-clock relative time)
                            t_sec = time.time() - self.start_wall_time
                            self.traj_records.append((t_sec, result['pose'].copy()))
                            # Stream SLAM map to remote viewer
                            self._send_frame(result['pose'], t_sec)

                    # Periodic logging
                    self.log_stats()

                except socket.timeout:
                    continue  # Normal timeout, check self.running
                except Exception as e:
                    print(f"❌ Error processing packet: {e}")
                    if self.args.debug:
                        import traceback
                        traceback.print_exc()

        except KeyboardInterrupt:
            print("\n⚠ Interrupted by user")

        finally:
            self.shutdown()

    def shutdown(self):
        """Cleanup and save results"""
        print("\n" + "="*70)
        print("SHUTTING DOWN")
        print("="*70)

        # Flush remaining frame
        print("Flushing final frame...")
        final_frame = self.frame_builder.flush(debug=self.args.debug)
        if final_frame:
            result = self.slam_pipeline.register_frame(final_frame, debug=self.args.debug)
            if result:
                self.pose_history.append(result['pose'].copy())

        # Close sockets
        if self.sock:
            self.sock.close()
            print("✓ UDP socket closed")

        if self.pub:
            self.pub.close()
            print("✓ ZMQ publisher closed")

        if self.zctx:
            self.zctx.term()

        # Final statistics
        print("\n" + "="*70)
        print("FINAL STATISTICS")
        print("="*70)
        self.log_stats(force=True)

        # Pose drift analysis
        if len(self.pose_history) > 1:
            self.analyze_pose_drift()

        # Save outputs (map/trajectory/metadata)
        if self.slam_stats.frames_processed > 0:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_dir = Path(self.args.output_dir).expanduser()
            if self.args.no_session_folder:
                session_dir = base_dir
            else:
                session_name = f"{timestamp}" + (f"_{self.args.run_name}" if self.args.run_name else "")
                session_dir = base_dir / session_name
            session_dir.mkdir(parents=True, exist_ok=True)

            # 1) Map (optional)
            if not self.args.no_save_map:
                map_file = session_dir / "map.pcd"
                self.slam_pipeline.save_map(str(map_file))

            # 2) Trajectory (always)
            self._save_trajectory(str(session_dir / "trajectory"))

            # 3) Metadata
            meta = {
                "timestamp": timestamp,
                "args": vars(self.args),
                "frames": self.slam_stats.frames_processed,
                "points": int(self.slam_stats.total_points_processed),
                "distance_m": float(self.slam_stats.distance_traveled),
            }
            with open(session_dir / "run_meta.json", "w") as f:
                json.dump(meta, f, indent=2)
            print(f"[OUT] Saved session to: {session_dir}")

            # 4) latest symlink
            if not self.args.no_session_folder:
                try:
                    latest = base_dir / "latest"
                    if latest.exists() or latest.is_symlink():
                        latest.unlink()
                    latest.symlink_to(session_dir.name)
                except Exception as e:
                    print(f"[OUT] latest symlink skipped: {e}")

        print("\n✓ Shutdown complete\n")


def parse_args():
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(
        description="G1 Live SLAM - LiDAR Stream Receiver & SLAM",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    # Network
    parser.add_argument('--listen-ip', type=str, default='0.0.0.0',
                        help='UDP listen IP address')
    parser.add_argument('--listen-port', type=int, default=9999,
                        help='UDP listen port')

    # Frame building
    parser.add_argument('--frame-rate', type=int, default=4,
                        help='Target frame rate (Hz, lower = denser frames for better SLAM)')

    # Filtering
    parser.add_argument('--min-range', type=float, default=0.1,
                        help='Minimum range (meters)')
    parser.add_argument('--max-range', type=float, default=30.0,
                        help='Maximum range (meters)')
    parser.add_argument('--self-filter-radius', type=float, default=0.30,
                        help='Robot self-filter XY radius (meters)')
    parser.add_argument('--self-filter-z', type=float, default=0.24,
                        help='Robot self-filter Z half-height (symmetric ±, meters)')

    # SLAM
    parser.add_argument('--voxel-size', type=float, default=0.15,
                        help='Voxel downsampling size (meters, indoor: 0.15-0.2, outdoor: 0.5-1.0)')
    parser.add_argument('--min-points-per-frame', type=int, default=800,
                        help='Skip frames with fewer points (stability)')
    parser.add_argument('--preset', type=str, default='indoor',
                        choices=['indoor', 'outdoor', 'custom'],
                        help='Configuration preset (applies ICP tuning)')

    # Output
    parser.add_argument('--no-save-map', action='store_true',
                        help='Do not save map on exit')
    parser.add_argument('--output-dir', type=str,
                        default='/home/unitree/AIM-Robotics/SLAM/maps',
                        help='Root directory to save map/trajectory')
    parser.add_argument('--run-name', type=str, default=None,
                        help='Optional run name appended to session folder (e.g., lab-corridor)')
    parser.add_argument('--no-session-folder', action='store_true',
                        help='Save directly under output-dir (no timestamped subfolder)')

    # Streaming
    parser.add_argument('--stream-enable', action='store_true',
                        help='Enable real-time ZMQ streaming to remote viewer')
    parser.add_argument('--stream-port', type=int, default=7609,
                        help='ZMQ PUB port for streaming')
    parser.add_argument('--stream-voxel', type=float, default=0.05,
                        help='Voxel size for stream downsampling (0 = disabled)')
    parser.add_argument('--stream-max-points', type=int, default=60000,
                        help='Max points per streamed frame')

    # Debug
    parser.add_argument('--debug', action='store_true',
                        help='Enable debug logging')

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    app = LiveSlam(args)
    app.run()
