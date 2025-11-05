#!/usr/bin/env python3
"""
YOLOv8 + RealSense Network Streaming - Sender (Jetson)
Real-time object detection with RealSense D435i, streaming to Mac via UDP
"""
import pyrealsense2 as rs
import numpy as np
import socket
import pickle
import time
import sys
import cv2
import struct
from ultralytics import YOLO  # type: ignore

# ============================================================
# Configuration
# ============================================================
MAC_IP = "192.168.123.99"
RGB_PORT = 8889
CHUNK_SIZE = 60000

YOLO_MODEL = "yolov8n.pt"
YOLO_CONF = 0.5

JETSON_WIFI_IP = "10.40.100.128"
REALSENSE_WIDTH = 640
REALSENSE_HEIGHT = 480
REALSENSE_FPS = 30

JPEG_QUALITY = 85
SEND_BUFFER_SIZE = 2 * 1024 * 1024

# ============================================================
# Helper Functions
# ============================================================
def send_chunked_data(sock, data, target_ip, target_port, sequence_id):
    """Split large data into chunks and send via UDP"""
    data_size = len(data)
    total_chunks = (data_size + CHUNK_SIZE - 1) // CHUNK_SIZE

    for chunk_idx in range(total_chunks):
        start = chunk_idx * CHUNK_SIZE
        end = min(start + CHUNK_SIZE, data_size)
        chunk_data = data[start:end]

        header = struct.pack('!III', sequence_id, chunk_idx, total_chunks)
        packet = header + chunk_data
        sock.sendto(packet, (target_ip, target_port))

# ============================================================
# Initialization
# ============================================================
print("=" * 60)
print("YOLOv8 + RealSense Network Streaming - Sender")
print("=" * 60)
print(f"\nConfiguration:")
print(f"  Target IP:    {MAC_IP}")
print(f"  RGB Port:     {RGB_PORT}")
print(f"  Resolution:   {REALSENSE_WIDTH}x{REALSENSE_HEIGHT} @ {REALSENSE_FPS}fps")
print(f"  YOLO Model:   {YOLO_MODEL}")
print(f"  YOLO Conf:    {YOLO_CONF}")
print(f"  Chunk size:   {CHUNK_SIZE // 1000}KB")
print("=" * 60)

# UDP Socket
print("\n[1/5] Initializing UDP socket...")
try:
    rgb_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rgb_sock.bind((JETSON_WIFI_IP, 0))
    rgb_sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, SEND_BUFFER_SIZE)
    print(f"  ✓ RGB socket created (target: {MAC_IP}:{RGB_PORT})")
except Exception as e:
    print(f"✗ Socket initialization failed: {e}")
    sys.exit(1)

# YOLO Model
print("\n[2/5] Loading YOLO model...")
try:
    model = YOLO(YOLO_MODEL)
    print(f"  ✓ YOLOv8 model loaded: {YOLO_MODEL}")
    print(f"  - Classes: {len(model.names)} (COCO dataset)")
    print(f"  - Device: {'CUDA' if model.device.type == 'cuda' else 'CPU'}")
except Exception as e:
    print(f"✗ YOLO initialization failed: {e}")
    sys.exit(1)

# RealSense Camera
print("\n[3/5] Initializing RealSense...")
try:
    pipeline = rs.pipeline()
    config = rs.config()
    config.enable_stream(rs.stream.depth, REALSENSE_WIDTH, REALSENSE_HEIGHT, rs.format.z16, REALSENSE_FPS)
    config.enable_stream(rs.stream.color, REALSENSE_WIDTH, REALSENSE_HEIGHT, rs.format.bgr8, REALSENSE_FPS)
    print(f"  - Depth stream: {REALSENSE_WIDTH}x{REALSENSE_HEIGHT} @ {REALSENSE_FPS}fps (z16)")
    print(f"  - Color stream: {REALSENSE_WIDTH}x{REALSENSE_HEIGHT} @ {REALSENSE_FPS}fps (bgr8)")
except Exception as e:
    print(f"✗ RealSense initialization failed: {e}")
    sys.exit(1)

# Start Pipeline
print("\n[4/5] Starting RealSense pipeline...")
pipeline_started = False
try:
    time.sleep(0.5)
    profile = pipeline.start(config)
    pipeline_started = True

    color_stream = profile.get_stream(rs.stream.color).as_video_stream_profile()
    intrinsics = color_stream.get_intrinsics()

    print(f"  ✓ Pipeline started")
    print(f"  - Resolution: {intrinsics.width}x{intrinsics.height}")
    print(f"  - Focal length: fx={intrinsics.fx:.1f}, fy={intrinsics.fy:.1f}")

    print("  - Stabilizing camera...")
    for i in range(30):
        pipeline.wait_for_frames()
    print("  ✓ Camera stabilized")

except Exception as e:
    print(f"✗ Pipeline start failed: {e}")
    print("  Hint: Wait 2-3 seconds and try again, or reconnect camera USB")
    if pipeline_started:
        pipeline.stop()
    sys.exit(1)

# ============================================================
# Main Loop
# ============================================================
print("\n[5/5] Streaming frames with YOLO detection...")
print("=" * 60)
print("Press Ctrl+C to stop")
print("=" * 60)

frame_count = 0
start_time = time.time()
last_print_time = start_time
yolo_time_total = 0.0

try:
    while True:
        frames = pipeline.wait_for_frames()
        depth_frame = frames.get_depth_frame()
        color_frame = frames.get_color_frame()

        if not depth_frame or not color_frame:
            continue

        depth_image = np.asanyarray(depth_frame.get_data())
        color_image = np.asanyarray(color_frame.get_data())

        # YOLO inference
        yolo_start = time.time()
        results = model(color_image, conf=YOLO_CONF, verbose=False)
        yolo_time_total += time.time() - yolo_start

        # Draw detections with distance
        annotated_image = results[0].plot()
        for box in results[0].boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2

            if 0 <= cx < REALSENSE_WIDTH and 0 <= cy < REALSENSE_HEIGHT:
                distance = depth_frame.get_distance(cx, cy)
                if distance > 0:
                    label = f"{distance:.1f}m"
                    cv2.putText(annotated_image, label, (x1, y1 - 25),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        # Encode and send
        try:
            _, rgb_encoded = cv2.imencode('.jpg', annotated_image, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
            rgb_data = pickle.dumps(rgb_encoded, protocol=pickle.HIGHEST_PROTOCOL)
            send_chunked_data(rgb_sock, rgb_data, MAC_IP, RGB_PORT, frame_count)
        except Exception as e:
            print(f"Warning: RGB send failed: {e}")

        frame_count += 1

        # Print stats every second
        current_time = time.time()
        if current_time - last_print_time >= 1.0:
            elapsed = current_time - start_time
            fps = frame_count / elapsed
            avg_yolo_time = (yolo_time_total / frame_count) * 1000
            num_detections = len(results[0].boxes)

            print(f"Frame {frame_count:5d} | FPS: {fps:5.1f} | "
                  f"YOLO: {avg_yolo_time:5.1f}ms | "
                  f"Objects: {num_detections:2d} | "
                  f"Size: {len(rgb_data)/1024:.1f}KB")

            last_print_time = current_time

except KeyboardInterrupt:
    print("\n\n" + "=" * 60)
    print("Stopping stream...")

except Exception as e:
    print(f"\n✗ Error during streaming: {e}")
    import traceback
    traceback.print_exc()

finally:
    print("\nCleaning up resources...")
    try:
        if pipeline_started:
            pipeline.stop()
            print("  ✓ Pipeline stopped")
            time.sleep(1)
    except Exception as e:
        print(f"  Warning: Pipeline stop error: {e}")

    try:
        rgb_sock.close()
        print("  ✓ Socket closed")
    except Exception as e:
        print(f"  Warning: Socket close error: {e}")

    elapsed = time.time() - start_time
    avg_fps = frame_count / elapsed if elapsed > 0 else 0
    avg_yolo = (yolo_time_total / frame_count) * 1000 if frame_count > 0 else 0

    print("=" * 60)
    print("Stream Statistics:")
    print(f"  Total frames:  {frame_count}")
    print(f"  Duration:      {elapsed:.1f}s")
    print(f"  Average FPS:   {avg_fps:.1f}")
    print(f"  Avg YOLO time: {avg_yolo:.1f}ms")
    print("=" * 60)
    print("✓ Stream stopped (safe to restart)")
    print("  Note: Wait 2-3 seconds before restarting")
