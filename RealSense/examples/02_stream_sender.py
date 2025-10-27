#!/usr/bin/env python3
"""
Phase 2: RealSense Network Streaming - Sender (Jetson)
Jetson에서 RealSense 카메라 데이터를 Mac으로 UDP 전송
"""
import pyrealsense2 as rs
import numpy as np
import socket
import pickle
import time
import sys
import cv2
import struct

# ============================================================
# Configuration
# ============================================================
MAC_IP = "192.168.123.99"  # Mac receiver IP
RGB_PORT = 8889      # RGB stream port
DEPTH_PORT = 8890    # Depth stream port
CHUNK_SIZE = 60000   # 60KB chunks (safe for UDP)

# ============================================================
# Helper function: Send large data with chunking
# ============================================================
def send_chunked_data(sock, data, target_ip, target_port, sequence_id):
    """Split large data into chunks and send via UDP"""
    data_size = len(data)
    total_chunks = (data_size + CHUNK_SIZE - 1) // CHUNK_SIZE  # Ceiling division

    for chunk_idx in range(total_chunks):
        start = chunk_idx * CHUNK_SIZE
        end = min(start + CHUNK_SIZE, data_size)
        chunk_data = data[start:end]

        # Create header: sequence_id (4 bytes) + chunk_index (4 bytes) + total_chunks (4 bytes)
        header = struct.pack('!III', sequence_id, chunk_idx, total_chunks)
        packet = header + chunk_data

        sock.sendto(packet, (target_ip, target_port))

print("=" * 60)
print("RealSense Network Streaming - Sender")
print("=" * 60)
print(f"\nConfiguration:")
print(f"  Target IP:    {MAC_IP}")
print(f"  RGB Port:     {RGB_PORT}")
print(f"  Depth Port:   {DEPTH_PORT}")
print(f"  Resolution:   640x480 @ 30fps")
print(f"  Chunk size:   {CHUNK_SIZE // 1000}KB")
print("=" * 60)

# ============================================================
# Initialize UDP sockets
# ============================================================
print("\n[1/4] Initializing UDP sockets...")
try:
    rgb_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    depth_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # Wi-Fi 인터페이스 바인딩
    rgb_sock.bind(("10.40.100.143", 0))
    depth_sock.bind(("10.40.100.143", 0))

    # Increase buffer size for large frames
    rgb_sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 2 * 1024 * 1024)  # 2MB
    depth_sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 2 * 1024 * 1024)  # 2MB

    print(f"  ✓ RGB socket created (target: {MAC_IP}:{RGB_PORT})")
    print(f"  ✓ Depth socket created (target: {MAC_IP}:{DEPTH_PORT})")
except Exception as e:
    print(f"✗ Socket initialization failed: {e}")
    sys.exit(1)

# ============================================================
# Initialize RealSense
# ============================================================
print("\n[2/4] Initializing RealSense...")
try:
    pipeline = rs.pipeline()
    config = rs.config()

    # Configure streams
    config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
    config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)

    print("  - Depth stream: 640x480 @ 30fps (z16)")
    print("  - Color stream: 640x480 @ 30fps (bgr8)")
except Exception as e:
    print(f"✗ RealSense initialization failed: {e}")
    sys.exit(1)

# ============================================================
# Start pipeline
# ============================================================
print("\n[3/4] Starting RealSense pipeline...")
try:
    profile = pipeline.start(config)

    # Get camera intrinsics
    color_stream = profile.get_stream(rs.stream.color).as_video_stream_profile()
    intrinsics = color_stream.get_intrinsics()

    print(f"  ✓ Pipeline started")
    print(f"  - Resolution: {intrinsics.width}x{intrinsics.height}")
    print(f"  - Focal length: fx={intrinsics.fx:.1f}, fy={intrinsics.fy:.1f}")

    # Stabilize camera
    print("  - Stabilizing camera...")
    for i in range(30):
        pipeline.wait_for_frames()
    print("  ✓ Camera stabilized")

except Exception as e:
    print(f"✗ Pipeline start failed: {e}")
    sys.exit(1)

# ============================================================
# Stream frames
# ============================================================
print("\n[4/4] Streaming frames...")
print("=" * 60)
print("Press Ctrl+C to stop")
print("=" * 60)

frame_count = 0
start_time = time.time()
last_print_time = start_time

try:
    while True:
        # Capture frames
        frames = pipeline.wait_for_frames()
        depth_frame = frames.get_depth_frame()
        color_frame = frames.get_color_frame()

        if not depth_frame or not color_frame:
            continue

        # Convert to numpy arrays
        depth_image = np.asanyarray(depth_frame.get_data())  # uint16
        color_image = np.asanyarray(color_frame.get_data())  # uint8, BGR

        # Compress and send RGB (JPEG encoding)
        try:
            # Encode RGB as JPEG (lossy compression, ~10-20x smaller)
            _, rgb_encoded = cv2.imencode('.jpg', color_image, [cv2.IMWRITE_JPEG_QUALITY, 85])
            rgb_data = pickle.dumps(rgb_encoded, protocol=pickle.HIGHEST_PROTOCOL)

            # Send with chunking
            send_chunked_data(rgb_sock, rgb_data, MAC_IP, RGB_PORT, frame_count)
        except Exception as e:
            print(f"Warning: RGB send failed: {e}")

        # Compress and send Depth (PNG encoding for lossless 16-bit)
        try:
            # Encode Depth as PNG (lossless compression for uint16)
            _, depth_encoded = cv2.imencode('.png', depth_image)
            depth_data = pickle.dumps(depth_encoded, protocol=pickle.HIGHEST_PROTOCOL)

            # Send with chunking
            send_chunked_data(depth_sock, depth_data, MAC_IP, DEPTH_PORT, frame_count)
        except Exception as e:
            print(f"Warning: Depth send failed: {e}")

        frame_count += 1

        # Print statistics every second
        current_time = time.time()
        if current_time - last_print_time >= 1.0:
            elapsed = current_time - start_time
            fps = frame_count / elapsed

            # Get depth statistics
            valid_depth = depth_image[depth_image > 0]
            if len(valid_depth) > 0:
                depth_mean = np.mean(valid_depth) / 1000.0  # Convert to meters
                depth_stats = f"depth_mean={depth_mean:.2f}m"
            else:
                depth_stats = "no_valid_depth"

            print(f"Frame {frame_count:5d} | FPS: {fps:5.1f} | "
                  f"RGB: {len(rgb_data)/1024:.1f}KB | "
                  f"Depth: {len(depth_data)/1024:.1f}KB | "
                  f"{depth_stats}")

            last_print_time = current_time

except KeyboardInterrupt:
    print("\n\n" + "=" * 60)
    print("Stopping stream...")

except Exception as e:
    print(f"\n✗ Error during streaming: {e}")

finally:
    # Cleanup
    pipeline.stop()
    rgb_sock.close()
    depth_sock.close()

    elapsed = time.time() - start_time
    avg_fps = frame_count / elapsed if elapsed > 0 else 0

    print("=" * 60)
    print("Stream Statistics:")
    print(f"  Total frames:  {frame_count}")
    print(f"  Duration:      {elapsed:.1f}s")
    print(f"  Average FPS:   {avg_fps:.1f}")
    print("=" * 60)
    print("✓ Stream stopped")
