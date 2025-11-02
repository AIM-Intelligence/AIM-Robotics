#!/usr/bin/env python3
"""
viewer_realtime_simple.py — Simple Real-time G1 SLAM Viewer (Mac)

Receives ZMQ stream from Jetson and renders with Open3D.
Uses modern gui.Application API for stable rendering.

Usage:
    python3 viewer_realtime_simple.py --server-ip 192.168.123.164 --port 7609 --flip-y --flip-z

Controls:
    Mouse - Rotate/Pan/Zoom
    Mouse Wheel - Zoom in/out
    Shift + Drag - Pan
    Double Click - Set rotation center
    R - Reset camera
    C - Clear accumulated points
    Q - Quit
"""
import argparse
import struct
import time
import numpy as np

try:
    import zmq
except ImportError:
    print("ERROR: ZMQ not installed. Run: pip3 install pyzmq")
    exit(1)

try:
    import open3d as o3d
    from open3d.visualization import gui, rendering
except ImportError:
    print("ERROR: Open3D not installed. Run: pip3 install open3d")
    exit(1)


# Protocol constants
MAGIC = b'G1PC'
VERSION = 1
HDR_FMT = '<4sBId16fI'
HDR_SIZE = struct.calcsize(HDR_FMT)


class SlamRealtimeViewer:
    def __init__(self, args):
        self.args = args
        self.running = True

        # ZMQ setup
        print(f"→ Connecting to tcp://{args.server_ip}:{args.port}...")
        self.ctx = zmq.Context.instance()
        self.sub = self.ctx.socket(zmq.SUB)
        self.sub.setsockopt(zmq.SUBSCRIBE, b"")
        self.sub.setsockopt(zmq.RCVTIMEO, 10)  # 10ms timeout
        self.sub.connect(f"tcp://{args.server_ip}:{args.port}")
        print(f"✓ Connected")

        # Stats
        self.frame_count = 0
        self.last_fps_time = time.time()
        self.fps_counter = 0

        # Trajectory
        self.trajectory_positions = []

        # Initialize GUI
        self.app = gui.Application.instance
        self.app.initialize()

        # Create window
        self.window = self.app.create_window("G1 SLAM — Real-time Map", 1280, 800)

        # Create SceneWidget (provides automatic orbit/pan/zoom controls)
        self.scene = gui.SceneWidget()
        self.scene.scene = rendering.Open3DScene(self.window.renderer)
        self.window.add_child(self.scene)

        # Prepare geometries
        self.pcd = o3d.geometry.PointCloud()
        self.trajectory_line = o3d.geometry.LineSet()
        self.coord_frame = o3d.geometry.TriangleMesh.create_coordinate_frame(size=1.0)

        # Materials
        self.pcd_mat = rendering.MaterialRecord()
        self.pcd_mat.shader = "defaultUnlit"
        self.pcd_mat.point_size = 2.0

        self.traj_mat = rendering.MaterialRecord()
        self.traj_mat.shader = "defaultUnlit"
        self.traj_mat.line_width = 2.0

        self.coord_mat = rendering.MaterialRecord()
        self.coord_mat.shader = "defaultUnlit"

        # Add geometries to scene
        self.scene.scene.add_geometry("pcd", self.pcd, self.pcd_mat)
        self.scene.scene.add_geometry("trajectory", self.trajectory_line, self.traj_mat)
        self.scene.scene.add_geometry("coord", self.coord_frame, self.coord_mat)

        # Initial camera setup
        bbox = o3d.geometry.AxisAlignedBoundingBox([-3, -3, -1], [3, 3, 2])
        self.scene.setup_camera(60.0, bbox, [0, 0, 0.5])

        # Background color (dark gray)
        self.scene.scene.set_background([0.1, 0.1, 0.15, 1.0])

        # Register keyboard events
        self.window.set_on_key(self.on_key)

        # Update interval
        self.update_interval = 0.01  # 10ms

        # Print usage
        print("\n" + "="*70)
        print("G1 SLAM Real-time Viewer")
        print("="*70)
        print("\nCamera Controls:")
        print("  Mouse Drag           → Orbit (rotate around center)")
        print("  Shift + Drag         → Pan (move look-at point)")
        print("  Mouse Wheel          → Zoom in/out")
        print("  Double Click         → Set rotation center")
        print("  R                    → Reset camera")
        print("  C                    → Clear buffer")
        print("  Q                    → Quit")
        print("="*70 + "\n")
        print("Waiting for SLAM data...\n")

        # Start update loop
        self.schedule_update()

    def on_key(self, e):
        """Handle keyboard events"""
        # R: Reset camera
        if e.key == gui.KeyName.R and e.type == gui.KeyEvent.DOWN:
            # Reset camera to show current map
            if len(self.trajectory_positions) > 0:
                pts = np.array(self.trajectory_positions)
                bbox = o3d.geometry.AxisAlignedBoundingBox(
                    pts.min(axis=0) - 1.0, pts.max(axis=0) + 1.0
                )
                center = bbox.get_center()
            else:
                bbox = o3d.geometry.AxisAlignedBoundingBox([-3, -3, -1], [3, 3, 2])
                center = [0, 0, 0.5]

            self.scene.setup_camera(60.0, bbox, center)
            print("✓ Camera reset")
            return True

        # C: Clear buffer
        if e.key == gui.KeyName.C and e.type == gui.KeyEvent.DOWN:
            self.trajectory_positions.clear()

            # Clear point cloud
            self.pcd.points = o3d.utility.Vector3dVector(np.zeros((0, 3)))
            self.pcd.colors = o3d.utility.Vector3dVector(np.zeros((0, 3)))

            # Clear trajectory
            self.trajectory_line.points = o3d.utility.Vector3dVector(np.zeros((0, 3)))
            self.trajectory_line.lines = o3d.utility.Vector2iVector(np.zeros((0, 2)))

            # Update scene
            self.scene.scene.remove_geometry("pcd")
            self.scene.scene.remove_geometry("trajectory")
            self.scene.scene.add_geometry("pcd", self.pcd, self.pcd_mat)
            self.scene.scene.add_geometry("trajectory", self.trajectory_line, self.traj_mat)

            print("✓ Buffer cleared")
            return True

        # Q: Quit application
        if e.key == gui.KeyName.Q and e.type == gui.KeyEvent.DOWN:
            self.running = False
            self.app.quit()
            return True

        return False

    def recv_frame(self):
        """Receive and parse one frame"""
        try:
            buf = self.sub.recv(zmq.NOBLOCK)
        except zmq.Again:
            return None

        if len(buf) < HDR_SIZE:
            return None

        # Parse header
        magic, ver, frame_id, t_sec, *pose16, count = struct.unpack(HDR_FMT, buf[:HDR_SIZE])

        if magic != MAGIC or ver != VERSION:
            if self.args.debug:
                print(f"[WARN] Invalid packet: magic={magic}, ver={ver}")
            return None

        # Parse points
        payload = buf[HDR_SIZE:]
        expected_size = count * 3 * 4  # 3 floats per point
        if len(payload) < expected_size:
            if self.args.debug:
                print(f"[WARN] Payload size mismatch: got {len(payload)}, expected {expected_size}")
            return None

        pts = np.frombuffer(payload, dtype=np.float32, count=count*3).reshape((-1, 3)).copy()
        pose = np.array(pose16, dtype=np.float32).reshape(4, 4)

        return {
            'frame_id': frame_id,
            't_sec': t_sec,
            'pose': pose,
            'points': pts
        }

    def apply_flips(self, pts):
        """Apply coordinate flips"""
        if self.args.flip_x:
            pts[:, 0] = -pts[:, 0]
        if self.args.flip_y:
            pts[:, 1] = -pts[:, 1]
        if self.args.flip_z:
            pts[:, 2] = -pts[:, 2]
        return pts

    def colorize_by_height(self, pts):
        """Color points by Z height (blue=low, green=mid, red=high)"""
        if len(pts) == 0:
            return np.zeros((0, 3))

        z = pts[:, 2]
        z_min = max(z.min(), -2.0)
        z_max = min(z.max(), 2.0)

        # Normalize to [0, 1]
        norm = np.clip((z - z_min) / max(z_max - z_min, 0.01), 0, 1)

        # Blue -> Green -> Red gradient
        colors = np.zeros((len(pts), 3))
        colors[:, 0] = norm                    # Red
        colors[:, 1] = 1.0 - np.abs(norm - 0.5) * 2  # Green (peak at 0.5)
        colors[:, 2] = 1.0 - norm              # Blue

        return colors

    def update_trajectory(self, pose):
        """Update robot trajectory visualization"""
        # Extract position from pose
        position = pose[:3, 3].copy()

        # Apply flips to position
        if self.args.flip_x:
            position[0] = -position[0]
        if self.args.flip_y:
            position[1] = -position[1]
        if self.args.flip_z:
            position[2] = -position[2]

        self.trajectory_positions.append(position)

        # Build line set
        if len(self.trajectory_positions) >= 2:
            points = np.array(self.trajectory_positions)
            lines = [[i, i+1] for i in range(len(points)-1)]

            self.trajectory_line.points = o3d.utility.Vector3dVector(points.astype(np.float64))
            self.trajectory_line.lines = o3d.utility.Vector2iVector(np.array(lines))

            # Color: green for trajectory
            colors = np.tile([0, 1, 0], (len(lines), 1))  # Green
            self.trajectory_line.colors = o3d.utility.Vector3dVector(colors)

            # Update scene (name-based, stable)
            self.scene.scene.remove_geometry("trajectory")
            self.scene.scene.add_geometry("trajectory", self.trajectory_line, self.traj_mat)

    def update_robot_frame(self, pose):
        """Update coordinate frame to follow robot position"""
        # Apply flips to pose
        pose_flipped = pose.copy()
        if self.args.flip_x:
            pose_flipped[0, 3] = -pose_flipped[0, 3]
        if self.args.flip_y:
            pose_flipped[1, 3] = -pose_flipped[1, 3]
        if self.args.flip_z:
            pose_flipped[2, 3] = -pose_flipped[2, 3]

        # Create new coordinate frame at robot pose
        coord_frame = o3d.geometry.TriangleMesh.create_coordinate_frame(size=0.5)
        coord_frame.transform(pose_flipped)

        # Update scene
        self.scene.scene.remove_geometry("coord")
        self.scene.scene.add_geometry("coord", coord_frame, self.coord_mat)

    def update_visualization(self, frame):
        """Update point cloud buffer and visualization"""
        pts = frame['points']
        pose = frame['pose']

        # Points are already in world coordinates (SLAM map)
        # Just apply coordinate flips if needed
        pts_world = self.apply_flips(pts)

        # Colorize by height
        colors = self.colorize_by_height(pts_world)

        # Update trajectory
        self.update_trajectory(pose)

        # Update point cloud
        self.pcd.points = o3d.utility.Vector3dVector(pts_world.astype(np.float64))
        self.pcd.colors = o3d.utility.Vector3dVector(colors.astype(np.float64))

        # Update scene (name-based, stable rendering)
        self.scene.scene.remove_geometry("pcd")
        self.scene.scene.add_geometry("pcd", self.pcd, self.pcd_mat)

        # Update coordinate frame to follow robot
        self.update_robot_frame(pose)

        self.frame_count += 1
        self.fps_counter += 1

        # FPS logging
        now = time.time()
        if now - self.last_fps_time >= 2.0:
            fps = self.fps_counter / (now - self.last_fps_time)
            print(f"[STATS] Frame #{self.frame_count}, FPS={fps:.1f}, Points={len(pts_world)}, Trajectory={len(self.trajectory_positions)}")
            self.last_fps_time = now
            self.fps_counter = 0

    def update_geometry(self):
        """Update geometry from ZMQ stream"""
        if not self.running:
            return False

        # Poll for frames (get latest)
        frame = None
        for _ in range(10):  # Try to get latest frame
            new_frame = self.recv_frame()
            if new_frame is not None:
                frame = new_frame
            else:
                break

        # Update visualization if we got a frame
        if frame is not None:
            self.update_visualization(frame)

        return True

    def schedule_update(self):
        """Schedule next geometry update"""
        if not self.running:
            return

        # Update geometry
        self.update_geometry()

        # Schedule next update
        gui.Application.instance.post_to_main_thread(
            self.window,
            lambda: self.schedule_update() if self.running else None
        )

    def run(self):
        """Run the main application loop"""
        print("[INFO] Starting viewer...\n")
        self.app.run()

        # Cleanup
        self.sub.close()
        self.ctx.term()
        print("\n✓ Viewer closed")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Simple Real-time G1 SLAM Point Cloud Viewer",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    parser.add_argument('--server-ip', type=str, required=True,
                        help='Jetson IP address (e.g., 192.168.123.164)')
    parser.add_argument('--port', type=int, default=7609,
                        help='ZMQ port')

    # Coordinate flips
    parser.add_argument('--flip-x', action='store_true',
                        help='Flip X axis')
    parser.add_argument('--flip-y', action='store_true',
                        help='Flip Y axis')
    parser.add_argument('--flip-z', action='store_true',
                        help='Flip Z axis')

    # Debug
    parser.add_argument('--debug', action='store_true',
                        help='Enable debug logging')

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    viewer = SlamRealtimeViewer(args)
    viewer.run()
