#!/usr/bin/env python3
"""
Phase 2: RealSense Network Streaming - Receiver (Mac)
Receive and display RealSense data from Jetson on Mac
"""
import socket
import numpy as np
import cv2
import sys
import time
import struct
from threading import Thread, Lock
from collections import defaultdict

# ============================================================
# Configuration
# ============================================================
RGB_PORT = 8889      # RGB stream port
DEPTH_PORT = 8890    # Depth stream port
HEADER_SIZE = 12     # 3 x 4 bytes (sequence_id, chunk_index, total_chunks)

print("=" * 60)
print("RealSense Network Streaming - Receiver")
print("=" * 60)
print(f"\nConfiguration:")
print(f"  RGB Port:     {RGB_PORT}")
print(f"  Depth Port:   {DEPTH_PORT}")
print(f"  Listening on: 0.0.0.0 (all interfaces)")
print("=" * 60)

# ============================================================
# Shared data
# ============================================================
rgb_image = None
depth_image = None
data_lock = Lock()

frame_count = {"rgb": 0, "depth": 0}
start_time = time.time()

# ============================================================
# Helper function: Receive chunked data
# ============================================================
def receive_chunked_data(sock):
    """Receive and reassemble chunked data"""
    chunks_buffer = defaultdict(dict)  # {sequence_id: {chunk_index: chunk_data}}

    while True:
        try:
            packet, addr = sock.recvfrom(65535)  # Max UDP packet size

            # Parse header
            header = packet[:HEADER_SIZE]
            sequence_id, chunk_index, total_chunks = struct.unpack('!III', header)
            chunk_data = packet[HEADER_SIZE:]

            # Store chunk
            chunks_buffer[sequence_id][chunk_index] = chunk_data

            # Check if all chunks received
            if len(chunks_buffer[sequence_id]) == total_chunks:
                # Reassemble data
                complete_data = b''.join(chunks_buffer[sequence_id][i] for i in range(total_chunks))

                # Clean up old sequences (keep only last 2)
                sequences = sorted(chunks_buffer.keys())
                for old_seq in sequences[:-2]:
                    del chunks_buffer[old_seq]

                yield complete_data

        except Exception as e:
            print(f"Chunk receive error: {e}")
            break

# ============================================================
# RGB receiver thread
# ============================================================
def receive_rgb():
    global rgb_image

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 2 * 1024 * 1024)  # 2MB buffer
    sock.bind(("0.0.0.0", RGB_PORT))

    print(f"✓ RGB receiver listening on port {RGB_PORT}")

    for complete_data in receive_chunked_data(sock):
        try:
            # Extract size header and encoded data
            size = struct.unpack('!I', complete_data[:4])[0]
            encoded_bytes = complete_data[4:4+size]

            # Convert bytes to numpy array
            encoded_image = np.frombuffer(encoded_bytes, dtype=np.uint8)

            # Decode JPEG
            image = cv2.imdecode(encoded_image, cv2.IMREAD_COLOR)

            with data_lock:
                rgb_image = image
                frame_count["rgb"] += 1

        except Exception as e:
            print(f"RGB decode error: {e}")

# ============================================================
# Depth receiver thread
# ============================================================
def receive_depth():
    global depth_image

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 2 * 1024 * 1024)  # 2MB buffer
    sock.bind(("0.0.0.0", DEPTH_PORT))

    print(f"✓ Depth receiver listening on port {DEPTH_PORT}")

    for complete_data in receive_chunked_data(sock):
        try:
            # Extract size header and encoded data
            size = struct.unpack('!I', complete_data[:4])[0]
            encoded_bytes = complete_data[4:4+size]

            # Convert bytes to numpy array
            encoded_image = np.frombuffer(encoded_bytes, dtype=np.uint8)

            # Decode PNG (preserves uint16)
            image = cv2.imdecode(encoded_image, cv2.IMREAD_UNCHANGED)

            with data_lock:
                depth_image = image
                frame_count["depth"] += 1

        except Exception as e:
            print(f"Depth decode error: {e}")

# ============================================================
# Start receiver threads
# ============================================================
print("\nStarting receiver threads...")
rgb_thread = Thread(target=receive_rgb, daemon=True)
depth_thread = Thread(target=receive_depth, daemon=True)

rgb_thread.start()
depth_thread.start()

time.sleep(1)  # Wait for threads to start

# ============================================================
# Display loop
# ============================================================
print("\n" + "=" * 60)
print("Waiting for frames...")
print("Press 'q' to quit")
print("=" * 60)

last_print_time = time.time()

try:
    while True:
        with data_lock:
            current_rgb = rgb_image.copy() if rgb_image is not None else None
            current_depth = depth_image.copy() if depth_image is not None else None

        # Display RGB
        if current_rgb is not None:
            # Add FPS overlay
            elapsed = time.time() - start_time
            fps_rgb = frame_count["rgb"] / elapsed if elapsed > 0 else 0

            display_rgb = current_rgb.copy()
            cv2.putText(display_rgb, f"RGB | FPS: {fps_rgb:.1f}", (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

            cv2.imshow("RealSense RGB", display_rgb)

        # Display Depth
        if current_depth is not None:
            # Convert depth to colormap for visualization
            # Normalize to 0-255 range (0-10m depth)
            depth_normalized = np.clip(current_depth / 10000.0 * 255, 0, 255).astype(np.uint8)
            depth_colormap = cv2.applyColorMap(depth_normalized, cv2.COLORMAP_JET)

            # Add FPS and depth info overlay
            elapsed = time.time() - start_time
            fps_depth = frame_count["depth"] / elapsed if elapsed > 0 else 0

            valid_depth = current_depth[current_depth > 0]
            if len(valid_depth) > 0:
                depth_mean = np.mean(valid_depth) / 1000.0  # Convert to meters
                depth_info = f"Mean: {depth_mean:.2f}m"
            else:
                depth_info = "No valid depth"

            cv2.putText(depth_colormap, f"Depth | FPS: {fps_depth:.1f}", (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.putText(depth_colormap, depth_info, (10, 60),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

            cv2.imshow("RealSense Depth", depth_colormap)

        # Print statistics every second
        current_time = time.time()
        if current_time - last_print_time >= 1.0:
            elapsed = current_time - start_time
            fps_rgb = frame_count["rgb"] / elapsed if elapsed > 0 else 0
            fps_depth = frame_count["depth"] / elapsed if elapsed > 0 else 0

            print(f"RGB: {frame_count['rgb']:5d} frames ({fps_rgb:5.1f} fps) | "
                  f"Depth: {frame_count['depth']:5d} frames ({fps_depth:5.1f} fps)")

            last_print_time = current_time

        # Check for quit
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break

except KeyboardInterrupt:
    print("\n\nStopping receiver...")

finally:
    cv2.destroyAllWindows()

    elapsed = time.time() - start_time
    avg_fps_rgb = frame_count["rgb"] / elapsed if elapsed > 0 else 0
    avg_fps_depth = frame_count["depth"] / elapsed if elapsed > 0 else 0

    print("\n" + "=" * 60)
    print("Stream Statistics:")
    print(f"  RGB frames:    {frame_count['rgb']:5d} ({avg_fps_rgb:.1f} fps)")
    print(f"  Depth frames:  {frame_count['depth']:5d} ({avg_fps_depth:.1f} fps)")
    print(f"  Duration:      {elapsed:.1f}s")
    print("=" * 60)
    print("✓ Receiver stopped")
