#!/usr/bin/env python3
"""
Check if Intel RealSense camera is connected and accessible.
Based on vibes project: list_realsense_devices.py
"""
import sys
import time

print("=" * 60)
print("Intel RealSense Camera Detection")
print("=" * 60)

# Step 1: Check pyrealsense2 import
try:
    import pyrealsense2 as rs
    print("✓ pyrealsense2 library found")
except ImportError as e:
    print(f"✗ pyrealsense2 not found: {e}")
    print("\nInstall with: pip3 install pyrealsense2")
    sys.exit(1)

# Step 2: Create context and query devices
print("\nSearching for RealSense devices...")
ctx = rs.context()
devices = ctx.query_devices()

num_devices = len(devices)
print(f"\nFound {num_devices} RealSense device(s)")

if num_devices == 0:
    print("\n" + "=" * 60)
    print("No RealSense camera detected!")
    print("=" * 60)
    print("\nTroubleshooting:")
    print("1. Check USB connection (USB 3.0 recommended)")
    print("2. Try different USB port")
    print("3. Check USB with: lsusb | grep -i intel")
    print("   (Should see: 8086:0b3a for D435i)")
    print("4. Check permissions: ls -l /dev/video*")
    print("5. Reconnect camera and try again")
    sys.exit(1)

# Step 3: Display device information
print("\n" + "=" * 60)
print("Device Information:")
print("=" * 60)

for i, device in enumerate(devices):
    print(f"\nDevice #{i+1}:")
    print(f"  Name:           {device.get_info(rs.camera_info.name)}")
    print(f"  Serial Number:  {device.get_info(rs.camera_info.serial_number)}")
    print(f"  Firmware:       {device.get_info(rs.camera_info.firmware_version)}")
    print(f"  USB Type:       {device.get_info(rs.camera_info.usb_type_descriptor)}")
    print(f"  Product ID:     {device.get_info(rs.camera_info.product_id)}")

    # List available sensors
    print(f"  Sensors:")
    for sensor in device.query_sensors():
        sensor_name = sensor.get_info(rs.camera_info.name)
        print(f"    - {sensor_name}")

# Step 4: Test basic access
print("\n" + "=" * 60)
print("Testing Basic Access...")
print("=" * 60)

pipeline = None
pipeline_started = False

try:
    pipeline = rs.pipeline()
    config = rs.config()

    # Try to enable basic streams
    config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
    config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)

    print("\nStarting pipeline...")
    profile = pipeline.start(config)
    pipeline_started = True

    # Wait for camera to stabilize (critical for avoiding "busy" state!)
    print("Stabilizing camera...")
    for i in range(30):  # Skip first 30 frames for full stabilization (same as basic_capture.py)
        pipeline.wait_for_frames()  # No timeout - wait as long as needed

    # Get one frame to verify
    print("Capturing test frame...")
    frames = pipeline.wait_for_frames()

    depth_frame = frames.get_depth_frame()
    color_frame = frames.get_color_frame()

    if depth_frame and color_frame:
        print("✓ Successfully received frames!")
        print(f"  Depth: {depth_frame.get_width()}x{depth_frame.get_height()}")
        print(f"  Color: {color_frame.get_width()}x{color_frame.get_height()}")
    else:
        print("✗ Failed to receive frames")

except Exception as e:
    print(f"✗ Error accessing camera: {e}")
    sys.exit(1)
finally:
    if pipeline and pipeline_started:
        try:
            pipeline.stop()
            time.sleep(0.5)  # Camera reinitialization time
        except:
            pass

print("\n" + "=" * 60)
print("✓ Camera is accessible and working!")
print("=" * 60)
print("\nNext steps:")
print("1. Run examples: cd /home/unitree/AIM-Robotics/RealSense/examples")
print("2. Test capture: python3 01_basic_capture.py")
print("3. Test streaming: python3 02_stream_sender.py")
