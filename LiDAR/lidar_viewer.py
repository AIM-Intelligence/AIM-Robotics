#!/usr/bin/env python3
"""
G1 LiDAR Real-time 3D Viewer - Open3D GUI
"""
import socket
import struct
import numpy as np
import open3d as o3d
from open3d.visualization import gui, rendering
import threading
import time
from matplotlib import cm

# ============================================
# Configuration
# ============================================

# UDP settings
UDP_IP = "0.0.0.0"
UDP_PORT = 8888

# Coordinate transformation
FLIP_X = False
FLIP_Y = True
FLIP_Z = True

# Distance filtering
MAX_RANGE = 15.0  # meters
MIN_RANGE = 0.1   # meters

# ============================================
# Global Variables
# ============================================
points_xyz = []
points_lock = threading.Lock()
running = True

# Color Lookup Table (pre-computed for speed)
COLORMAP_SIZE = 256
COLORMAP_LUT = cm.jet(np.linspace(0, 1, COLORMAP_SIZE))[:, :3]


def udp_receiver():
    """
    UDP receiver thread - optimized version
    Receives point cloud data and buffers them
    """
    global points_xyz, running

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((UDP_IP, UDP_PORT))
    sock.setblocking(False)

    print(f"UDP listening on {UDP_IP}:{UDP_PORT}")

    local_buffer = []

    while running:
        try:
            data, addr = sock.recvfrom(65536)
            num_points = len(data) // 13

            for i in range(num_points):
                offset = i * 13
                x, y, z = struct.unpack('fff', data[offset:offset+12])

                # Apply coordinate transformation
                if FLIP_X:
                    x = -x
                if FLIP_Y:
                    y = -y
                if FLIP_Z:
                    z = -z

                # Distance filtering (remove noise)
                distance = np.sqrt(x*x + y*y + z*z)
                if MIN_RANGE < distance < MAX_RANGE:
                    local_buffer.append([x, y, z])

            # Periodically copy to main buffer
            if len(local_buffer) > 1000:
                with points_lock:
                    points_xyz.extend(local_buffer)
                    # Limit buffer size
                    if len(points_xyz) > 70000:
                        points_xyz = points_xyz[-50000:]
                local_buffer.clear()

        except BlockingIOError:
            time.sleep(0.001)
        except Exception as e:
            if running:
                print(f"❌ Error: {e}")
            break

    sock.close()


class LiDARWindow:
    """
    Main window class for LiDAR visualization
    Uses Open3D GUI for Rhino-style camera controls
    """

    def __init__(self):
        self.app = gui.Application.instance
        self.app.initialize()

        # Create window
        self.window = self.app.create_window("G1 LiDAR - Rhino Style", 1280, 720)

        # Create SceneWidget (provides automatic orbit/pan/zoom controls)
        self.scene = gui.SceneWidget()
        self.scene.scene = rendering.Open3DScene(self.window.renderer)
        self.window.add_child(self.scene)

        # Prepare point cloud
        self.pcd = o3d.geometry.PointCloud()
        self.mat = rendering.MaterialRecord()
        self.mat.shader = "defaultUnlit"
        self.mat.point_size = 2.0

        # Add coordinate frame at origin
        self.coord_frame = o3d.geometry.TriangleMesh.create_coordinate_frame(size=0.5)
        coord_mat = rendering.MaterialRecord()
        coord_mat.shader = "defaultUnlit"

        # Add to scene
        self.scene.scene.add_geometry("pcd", self.pcd, self.mat)
        self.scene.scene.add_geometry("coord", self.coord_frame, coord_mat)

        # Initial camera setup
        bbox = o3d.geometry.AxisAlignedBoundingBox([-3, -3, 0], [3, 3, 3])
        self.scene.setup_camera(60.0, bbox, [0, 0, 0.5])

        # Background color (dark gray)
        self.scene.scene.set_background([0.05, 0.05, 0.05, 1.0])

        # Register keyboard events
        self.window.set_on_key(self.on_key)

        # Timer variables
        self.frame_count = 0
        self.last_fps_time = time.time()
        self.update_interval = 0.05  # 50ms = 20 FPS

        # Print usage information
        print("\n" + "="*60)
        print("G1 LiDAR Viewer")
        print("="*60)
        print("\nCamera Controls:")
        print("  Mouse Drag           → Orbit (rotate around center)")
        print("  Shift + Drag         → Pan (move look-at point)")
        print("  Mouse Wheel          → Zoom in/out")
        print("  Double Click         → Set rotation center")
        print("  R                    → Reset camera")
        print("  Q                    → Quit")
        print(f"\nPerformance:")
        print(f"  Range: {MIN_RANGE}-{MAX_RANGE}m")
        print("="*60 + "\n")
        print("Waiting for data...\n")

        # Start update loop
        self.schedule_update()

    def on_key(self, e):
        """Handle keyboard events"""
        # R: Reset camera
        if e.key == gui.KeyName.R and e.type == gui.KeyEvent.DOWN:
            with points_lock:
                if len(points_xyz) > 0:
                    arr = np.array(points_xyz)
                    bbox = o3d.geometry.AxisAlignedBoundingBox(
                        arr.min(axis=0), arr.max(axis=0)
                    )
                    center = bbox.get_center()
                else:
                    bbox = o3d.geometry.AxisAlignedBoundingBox([-3, -3, 0], [3, 3, 3])
                    center = [0, 0, 0.5]

            self.scene.setup_camera(60.0, bbox, center)
            print("✓ Camera reset")
            return True

        # Q: Quit application
        if e.key == gui.KeyName.Q and e.type == gui.KeyEvent.DOWN:
            global running
            running = False
            self.app.quit()
            return True

        return False

    def update_geometry(self):
        """
        Update point cloud geometry
        Returns True if updated successfully, False otherwise
        """
        # Copy points from buffer
        with points_lock:
            if len(points_xyz) == 0:
                return False
            arr = np.array(points_xyz, dtype=np.float32)

        # Calculate colors using LUT (optimized)
        distances = np.linalg.norm(arr, axis=1)
        d_min, d_max = distances.min(), distances.max()
        if d_max > d_min:
            normalized = (distances - d_min) / (d_max - d_min)
        else:
            normalized = np.zeros_like(distances)

        # Use Lookup Table
        indices = (normalized * 255).astype(np.uint8)
        colors = COLORMAP_LUT[indices]

        # Update point cloud
        self.pcd.points = o3d.utility.Vector3dVector(arr)
        self.pcd.colors = o3d.utility.Vector3dVector(colors)

        # Update scene
        self.scene.scene.remove_geometry("pcd")
        self.scene.scene.add_geometry("pcd", self.pcd, self.mat)

        # Print FPS every 100 frames
        self.frame_count += 1
        if self.frame_count % 100 == 0:
            current_time = time.time()
            elapsed = current_time - self.last_fps_time
            fps = 100 / elapsed
            print(f"✓ Frame {self.frame_count}: {len(arr):,} points | {fps:.1f} FPS")
            self.last_fps_time = current_time

        return True

    def schedule_update(self):
        """Schedule next geometry update"""
        if not running:
            return

        # Update geometry
        self.update_geometry()

        # Schedule next update
        gui.Application.instance.post_to_main_thread(
            self.window,
            lambda: self.schedule_update() if running else None
        )
 
    def run(self):
        """Run the main application loop"""
        self.app.run()


def main():
    """Main entry point"""
    # Start UDP receiver thread
    receiver = threading.Thread(target=udp_receiver, daemon=True)
    receiver.start()

    # Run GUI
    try:
        window = LiDARWindow()
        window.run()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        global running
        running = False
        receiver.join(timeout=1.0)
        print("\nViewer closed")


if __name__ == "__main__":
    main()
