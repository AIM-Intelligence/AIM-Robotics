#!/usr/bin/env python3
"""
YOLOv8 + RealSense Network Streaming - Receiver (Mac)
Receives and displays YOLO detection results from Jetson via UDP
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
RGB_PORT = 8889
HEADER_SIZE = 12
RECV_BUFFER_SIZE = 2 * 1024 * 1024
MAX_UDP_PACKET = 65535

# ============================================================
# Shared State
# ============================================================
rgb_image = None
data_lock = Lock()
frame_count = 0
start_time = time.time()

# ============================================================
# Helper Functions
# ============================================================
def receive_chunked_data(sock):
    """Receive and reassemble chunked UDP data"""
    chunks_buffer = defaultdict(dict)

    while True:
        try:
            packet, addr = sock.recvfrom(MAX_UDP_PACKET)

            header = packet[:HEADER_SIZE]
            sequence_id, chunk_index, total_chunks = struct.unpack('!III', header)
            chunk_data = packet[HEADER_SIZE:]

            chunks_buffer[sequence_id][chunk_index] = chunk_data

            if len(chunks_buffer[sequence_id]) == total_chunks:
                complete_data = b''.join(chunks_buffer[sequence_id][i] for i in range(total_chunks))

                sequences = sorted(chunks_buffer.keys())
                for old_seq in sequences[:-2]:
                    del chunks_buffer[old_seq]

                yield complete_data

        except Exception as e:
            print(f"Chunk receive error: {e}")
            break

def receive_rgb():
    """RGB receiver thread"""
    global rgb_image, frame_count

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, RECV_BUFFER_SIZE)
    sock.bind(("0.0.0.0", RGB_PORT))

    print(f"✓ RGB receiver listening on port {RGB_PORT}")

    for complete_data in receive_chunked_data(sock):
        try:
            # Extract size header and encoded data
            size = struct.unpack('!I', complete_data[:4])[0]
            encoded_bytes = complete_data[4:4+size]

            # Convert bytes to numpy array
            encoded_image = np.frombuffer(encoded_bytes, dtype=np.uint8)
            image = cv2.imdecode(encoded_image, cv2.IMREAD_COLOR)

            with data_lock:
                rgb_image = image
                frame_count += 1

        except Exception as e:
            print(f"RGB decode error: {e}")

# ============================================================
# Main
# ============================================================
print("=" * 60)
print("YOLOv8 + RealSense Network Streaming - Receiver")
print("=" * 60)
print(f"\nConfiguration:")
print(f"  RGB Port:     {RGB_PORT}")
print(f"  Listening on: 0.0.0.0 (all interfaces)")
print("=" * 60)

print("\nStarting receiver thread...")
rgb_thread = Thread(target=receive_rgb, daemon=True)
rgb_thread.start()
time.sleep(1)

print("\n" + "=" * 60)
print("Waiting for YOLO frames...")
print("Press 'q' to quit")
print("=" * 60)

last_print_time = time.time()

try:
    while True:
        with data_lock:
            current_rgb = rgb_image.copy() if rgb_image is not None else None

        if current_rgb is not None:
            elapsed = time.time() - start_time
            fps = frame_count / elapsed if elapsed > 0 else 0

            display_rgb = current_rgb.copy()
            cv2.putText(display_rgb, f"YOLO Detection | FPS: {fps:.1f}", (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

            cv2.imshow("YOLO + RealSense", display_rgb)

        current_time = time.time()
        if current_time - last_print_time >= 1.0:
            elapsed = current_time - start_time
            fps = frame_count / elapsed if elapsed > 0 else 0
            print(f"Frames: {frame_count:5d} | FPS: {fps:5.1f}")
            last_print_time = current_time

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break

except KeyboardInterrupt:
    print("\n\nStopping receiver...")

finally:
    cv2.destroyAllWindows()

    elapsed = time.time() - start_time
    avg_fps = frame_count / elapsed if elapsed > 0 else 0

    print("\n" + "=" * 60)
    print("Stream Statistics:")
    print(f"  Total frames:  {frame_count:5d}")
    print(f"  Average FPS:   {avg_fps:.1f}")
    print(f"  Duration:      {elapsed:.1f}s")
    print("=" * 60)
    print("✓ Receiver stopped")
