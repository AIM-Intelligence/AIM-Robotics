#!/usr/bin/env python3
"""
Phase 1: Basic RealSense Frame Capture
로컬 테스트용 - RGB와 Depth 프레임 캡처 및 분석
"""
import pyrealsense2 as rs
import numpy as np
import sys
import time

print("=" * 60)
print("RealSense D435i - Basic Frame Capture")
print("=" * 60)

# RealSense 초기화
print("\n[1/5] Initializing RealSense...")
try:
    pipeline = rs.pipeline()
    config = rs.config()

    # 스트림 설정
    config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
    config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)

    print("  - Depth stream: 640x480 @ 30fps (z16)")
    print("  - Color stream: 640x480 @ 30fps (bgr8)")

except Exception as e:
    print(f"✗ Initialization failed: {e}")
    sys.exit(1)

# 파이프라인 시작
print("\n[2/5] Starting pipeline...")
try:
    profile = pipeline.start(config)

    # 인트린식 파라미터 가져오기
    color_stream = profile.get_stream(rs.stream.color).as_video_stream_profile()
    intrinsics = color_stream.get_intrinsics()

    print(f"  ✓ Pipeline started")
    print(f"  - Resolution: {intrinsics.width}x{intrinsics.height}")
    print(f"  - Focal length: fx={intrinsics.fx:.1f}, fy={intrinsics.fy:.1f}")
    print(f"  - Principal point: cx={intrinsics.ppx:.1f}, cy={intrinsics.ppy:.1f}")

except Exception as e:
    print(f"✗ Pipeline start failed: {e}")
    sys.exit(1)

# 안정화를 위해 몇 프레임 건너뛰기
print("\n[3/5] Waiting for camera to stabilize...")
for i in range(30):
    pipeline.wait_for_frames()
print("  ✓ Camera stabilized (30 frames skipped)")

# 프레임 캡처
print("\n[4/5] Capturing frames...")
try:
    frames = pipeline.wait_for_frames()

    depth_frame = frames.get_depth_frame()
    color_frame = frames.get_color_frame()

    if not depth_frame or not color_frame:
        raise RuntimeError("Failed to capture frames")

    # NumPy 배열로 변환
    depth_image = np.asanyarray(depth_frame.get_data())  # uint16, mm 단위
    color_image = np.asanyarray(color_frame.get_data())  # uint8, BGR

    print(f"  ✓ Frames captured successfully")
    print(f"  - Depth shape: {depth_image.shape}, dtype: {depth_image.dtype}")
    print(f"  - Color shape: {color_image.shape}, dtype: {color_image.dtype}")

except Exception as e:
    print(f"✗ Frame capture failed: {e}")
    pipeline.stop()
    sys.exit(1)

# 데이터 분석
print("\n[5/5] Analyzing data...")

# Depth 통계
valid_depth = depth_image[depth_image > 0]  # 0은 무효값
if len(valid_depth) > 0:
    depth_min = np.min(valid_depth)
    depth_max = np.max(valid_depth)
    depth_mean = np.mean(valid_depth)
    depth_median = np.median(valid_depth)

    print(f"\n  Depth statistics:")
    print(f"    - Valid pixels: {len(valid_depth):,} / {depth_image.size:,} ({len(valid_depth)/depth_image.size*100:.1f}%)")
    print(f"    - Min: {depth_min} mm ({depth_min/1000:.2f} m)")
    print(f"    - Max: {depth_max} mm ({depth_max/1000:.2f} m)")
    print(f"    - Mean: {depth_mean:.0f} mm ({depth_mean/1000:.2f} m)")
    print(f"    - Median: {depth_median:.0f} mm ({depth_median/1000:.2f} m)")

    # Depth distribution
    print(f"\n  Depth distribution:")
    ranges = [(0, 1000), (1000, 2000), (2000, 3000), (3000, 5000), (5000, 10000), (10000, float('inf'))]
    for min_d, max_d in ranges:
        count = np.sum((valid_depth >= min_d) & (valid_depth < max_d))
        pct = count / len(valid_depth) * 100
        max_label = f"{max_d/1000:.1f}m" if max_d != float('inf') else "inf"
        print(f"    {min_d/1000:.1f}m - {max_label}: {count:6,} pixels ({pct:5.1f}%)")
else:
    print(f"  ✗ No valid depth data")

# Color 통계
print(f"\n  Color statistics:")
print(f"    - Overall: min={np.min(color_image)}, max={np.max(color_image)}, mean={np.mean(color_image):.1f}")
print(f"    - Per channel:")
for i, channel in enumerate(['B', 'G', 'R']):
    channel_data = color_image[:, :, i]
    print(f"      {channel}: min={np.min(channel_data)}, max={np.max(channel_data)}, mean={np.mean(channel_data):.1f}")

# Sample pixel values
print(f"\n  Sample pixel values (center of image):")
cy, cx = depth_image.shape[0] // 2, depth_image.shape[1] // 2
print(f"    Center ({cy}, {cx}):")
print(f"      Depth: {depth_image[cy, cx]} mm ({depth_image[cy, cx]/1000:.2f} m)")
print(f"      Color (BGR): {color_image[cy, cx]}")

print(f"\n    Depth 3x3 region around center (in mm):")
for dy in range(-1, 2):
    row_values = []
    for dx in range(-1, 2):
        val = depth_image[cy+dy, cx+dx]
        row_values.append(f"{val:5d}")
    print("      " + "  ".join(row_values))

# 정리
pipeline.stop()
time.sleep(0.5)  # 카메라 재초기화를 위한 대기

print("\n" + "=" * 60)
print("✓ Capture and analysis complete!")
print("=" * 60)
print("\nNext steps:")
print("1. If data looks good, proceed to Phase 2")
print("2. Run: python3 02_stream_sender.py (network streaming)")
print("=" * 60)
