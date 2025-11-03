# G1 LiDAR SLAM System

**Real-time 3D SLAM with Livox Mid-360 LiDAR on Unitree G1 Robot**

---

## Overview

Production-ready SLAM system for the Unitree G1 humanoid robot using Livox Mid-360 LiDAR and KISS-ICP odometry. Features C++ optimized packet processing, real-time map streaming, and trajectory recording.

**Key Features:**
- **C++ Optimized Backend** (27% faster than Python, 15% CPU reduction)
- **Real-time Streaming** (ZMQ visualization on Mac/PC)
- **Structured Protocol** (v1 with CRC32 integrity checking)
- **Robust Frame Building** (time-based with packet loss detection)
- **Production Ready** (2000 pps, <10ms latency, 10Hz SLAM)

**Performance:**
- Frame processing: **40 ms/frame** (Phase 1: 7.68ms, Phase 2: 3.25ms, SLAM: 29.13ms)
- CPU usage: ~15% (single core on Jetson Orin NX)
- Network bandwidth: ~10 Mbit/s (indoor, full resolution)
- Map quality: Sub-centimeter accuracy at walking speed

---

## Quick Start

### Prerequisites

**Hardware:**
- Unitree G1 robot with Jetson Orin NX (or compatible)
- Livox Mid-360 LiDAR
- Wired Ethernet connection (LiDAR -> Jetson)
- Optional: Mac/PC for real-time visualization

**Network Configuration:**
```bash
# LiDAR must be on 192.168.123.0/24 subnet
# Livox Mid-360 default IP: 192.168.123.120
# Jetson interface: 192.168.123.164 (or any IP in same subnet)

# Verify network
ping 192.168.123.120
```

**Software Dependencies:**
```bash
# On Jetson (G1 robot)
pip3 install numpy open3d kiss-icp pybind11 pyzmq

# On Mac/PC (for viewer, optional)
pip3 install open3d pyzmq
```

---

### Step-by-Step Execution

#### **Terminal 1: Start LiDAR Transmitter** (on Jetson)

```bash
cd /home/unitree/AIM-Robotics/SLAM/lidar_tx

# Build (first time only)
./build.sh

# Run transmitter (indoor, 15m range)
./build/lidar_stream config.json 127.0.0.1 9999 --max-range 15.0
```

**Expected Output:**
```
========================================
Livox LiDAR Stream (v1)
========================================
Initializing Livox SDK...
 LiDAR connected: Mid-360 (SN: 1234567890)
 Streaming to 127.0.0.1:9999
 Range filter: 0.1 - 15.0 m
 Downsampling: 1x (disabled)

[TX] Packets: 1054/s, Points: 105400/s, Bandwidth: 9.8 Mbit/s
```

---

#### **Terminal 2: Start SLAM Receiver** (on Jetson)

```bash
cd /home/unitree/AIM-Robotics/SLAM/slam_rx

# Build C++ modules (first time only)
./build.sh clean

# Run SLAM (indoor preset, 10Hz)
python3 live_slam.py \
    --frame-rate 10 \
    --max-range 15.0 \
    --listen-port 9999 \
    --stream-enable \
    --stream-port 7609
```

**Expected Output:**
```
======================================================================
G1 Live SLAM
======================================================================
Frame rate:       10 Hz
Range:            0.1 - 15.0 m
Voxel size:       0.15 m
Self-filter:      r=0.3m, z=->0.24m (symmetric)
Min pts/frame:    800
Preset:           indoor (ICP tuning applied)
Debug:            False
======================================================================

 UDP socket listening on 0.0.0.0:9999
Listening for LiDAR packets... (Ctrl+C to stop)

======================================================================
[RX] Packets: 1054 (1054.0 pps), Valid: 1054
     Errors: CRC=0, Magic=0, Len=0
[FRAME] Built: 10, Packets: 1054, Avg pts/frame: 7200
        Late: 0, Gaps: 0, Reorder: 0
[SLAM] Processed: 10, Skipped: 0
       Position: [0.52, -0.12, 0.03], Distance: 0.53m
       Map points: 45230
======================================================================
```

---

#### **Terminal 3: Real-time Viewer** (on Mac/PC, optional)

```bash
cd /home/unitree/AIM-Robotics/SLAM

# Run viewer (connect to Jetson)
python3 viewer_realtime.py \
    --server-ip 192.168.123.164 \
    --port 7609 \
    --flip-y --flip-z
```

**Viewer Controls:**
- Mouse drag: Rotate view
- Scroll: Zoom
- Shift + Drag: Pan
- **R**: Reset camera
- **C**: Clear accumulated points
- **Q**: Quit

---

### Stopping and Viewing Results

**Stop SLAM (Ctrl+C in Terminal 2):**
```
^C
Shutdown signal received...

======================================================================
POSE DRIFT ANALYSIS (719 samples)
======================================================================
Mean Δt per frame: 0.0034 m
Std deviation:     0.0018 m
Max Δt:            0.0087 m
PASS: Mean drift < 0.02m (stationary stability)
======================================================================

Saving trajectory: maps/20251103_234504/trajectory.csv
Saving map: maps/20251103_234504/map.pcd
Map saved: 1234567 points

Session saved to: maps/20251103_234504/
  - map.pcd (1.7 MB)
  - trajectory.csv (TUM format)
  - run_meta.json (statistics)
```

**View Offline Results:**
```bash
# View map + trajectory
python3 viz_map_traj.py \
    --map maps/latest/map.pcd \
    --traj maps/latest/trajectory.csv
```

---


## Architecture

### System Diagram

```
+------------------------------------------------------------------+
|  Livox Mid-360 LiDAR                                             |
|  IP: 192.168.123.120 (fixed)                                     |
|  Output: ~100,000 points/sec                                     |
+-----------------------------+------------------------------------+
                              | Livox SDK2 (Ethernet)
                              v
+------------------------------------------------------------------+
|  lidar_tx (C++ Transmitter)                                      |
|  - Livox SDK2 integration                                        |
|  - Range filtering (min/max)                                     |
|  - Downsampling (optional)                                       |
|  - Protocol packaging (27B header + points)                      |
|  - UDP streaming (~1000 pps, ~10 Mbit/s)                         |
+-----------------------------+------------------------------------+
                              | UDP (127.0.0.1:9999 or remote)
                              v
+------------------------------------------------------------------+
|  slam_rx (Python + C++ Receiver)                                 |
|                                                                  |
|  Phase 1: Protocol Parser (C++)                                  |
|  - Parse 27B header (magic, timestamp, seq, CRC)                 |
|  - Validate packet integrity                                     |
|  - Extract XYZ points + intensity                                |
|  - Time: 7.68 ms/frame                                           |
|                                                                  |
|  Phase 2: Frame Builder (C++)                                    |
|  - Accumulate packets by device timestamp                        |
|  - Time-based framing (10Hz = 0.1s windows)                      |
|  - Detect packet loss, reordering                                |
|  - Time: 3.25 ms/frame                                           |
|                                                                  |
|  Phase 3: SLAM Pipeline (Python + KISS-ICP C++)                  |
|  - Range filtering (min/max)                                     |
|  - Self-occlusion filtering (robot body)                         |
|  - Voxel downsampling                                            |
|  - KISS-ICP odometry (pose estimation)                           |
|  - Map accumulation                                              |
|  - Time: 29.13 ms/frame                                          |
|                                                                  |
+--------+------------------------+--------------------------------+
         |                        |
         | ZMQ Stream             | Save on exit
         | (if --stream-enable)   |
         v                        v
+------------------+    +---------------------+
|  viewer_realtime |    |  maps/YYYYMMDD/     |
|  (Mac/PC)        |    |  - map.pcd          |
|  Real-time viz   |    |  - trajectory.csv   |
+------------------+    |  - run_meta.json    |
                        +---------------------+
```

### Data Flow

```
LiDAR Point -> Livox SDK2 -> lidar_tx -> UDP Packet -> slam_rx
                                                          |
                                             Protocol Parser (C++)
                                                          |
                                              Frame Builder (C++)
                                                          |
                                            SLAM Pipeline (KISS-ICP)
                                                          |
                                      +-------------------+-------------------+
                                      |                   |                   |
                                      v                   v                   v
                                   Pose                 Map            Trajectory
                                                          |
                                              ZMQ Stream (optional)
                                                          |
                                                          v
                                                  Remote Viewer
```
---
## Project Structure

```
/home/unitree/AIM-Robotics/SLAM/
├── README.md                    # This file
├── .gitignore                   # Git ignore rules
│
├── lidar_tx/                    # LiDAR Transmitter (C++)
│   ├── lidar_stream.cpp         # Main executable source
│   ├── CMakeLists.txt           # Build configuration
│   ├── build.sh                 # Build wrapper script
│   ├── config.json              # Livox SDK2 configuration
│   ├── PROTOCOL.md              # Protocol specification (v1)
│   ├── README.md                # Transmitter documentation
│   └── build/
│       └── lidar_stream         # Compiled executable
│
├── slam_rx/                     # SLAM Receiver (C++ optimized)
│   ├── live_slam.py             # Main entry point
│   ├── slam_pipeline.py         # KISS-ICP wrapper
│   ├── build.sh                 # C++ module build script
│   ├── README.md                # Receiver documentation
│   ├── cpp/                     # C++ backend modules
│   │   ├── CMakeLists.txt
│   │   ├── include/
│   │   │   ├── lidar_protocol_cpp.hpp
│   │   │   └── frame_builder_cpp.hpp
│   │   ├── src/
│   │   │   ├── lidar_protocol_cpp.cpp
│   │   │   ├── lidar_protocol_pybind.cpp
│   │   │   ├── frame_builder_cpp.cpp
│   │   │   └── frame_builder_pybind.cpp
│   │   └── build/
│   ├── lidar_protocol_cpp.*.so  # Compiled Python module
│   └── frame_builder_cpp.*.so   # Compiled Python module
│
├── slam_rx_python/              # Python Reference (Archived)
│   ├── live_slam.py             # Pure Python implementation
│   ├── lidar_protocol.py        # Protocol parser (Python)
│   ├── frame_builder.py         # Frame builder (Python)
│   ├── slam_pipeline.py         # SLAM pipeline (Python)
│   └── README.md                # Archive documentation
│
├── maps/                        # Generated Output
│   ├── YYYYMMDD_HHMMSS/         # Session folders
│   │   ├── map.pcd              # Point cloud map
│   │   ├── trajectory.csv       # TUM format trajectory
│   │   ├── trajectory.npy       # NumPy trajectory backup
│   │   └── run_meta.json        # Run statistics
│   └── latest/                  # Symlink to most recent
│
├── viewer_realtime.py           # Real-time ZMQ viewer
└── viz_map_traj.py              # Offline map/trajectory viewer
```


---

## Component Documentation

Each component has detailed documentation in its own directory:

| Component | Description | Documentation |
|-----------|-------------|---------------|
| **lidar_tx** | C++ LiDAR transmitter with Livox SDK2 integration | [lidar_tx/README.md](lidar_tx/README.md) |
| **slam_rx** | C++ optimized SLAM receiver (production) | [slam_rx/README.md](slam_rx/README.md) |
| **slam_rx_python** | Python reference implementation (archived) | [slam_rx_python/README.md](slam_rx_python/README.md) |
| **Protocol Spec** | Packet format, CRC, versioning | [lidar_tx/PROTOCOL.md](lidar_tx/PROTOCOL.md) |

---

## Network Setup

### Single Machine (Jetson only)

**Configuration:**
- LiDAR IP: `192.168.123.120` (fixed, cannot change)
- Jetson IP: `192.168.123.164` (or any IP in 192.168.123.0/24)
- Transmitter target: `127.0.0.1:9999` (localhost)
- Receiver listens: `0.0.0.0:9999`

**Setup:**
```bash
# 1. Configure Jetson network interface
sudo ifconfig eth0 192.168.123.164 netmask 255.255.255.0

# 2. Verify LiDAR connectivity
ping 192.168.123.120

# 3. Run transmitter + receiver (see Quick Start)
```

---

### Multi-Machine (Jetson + Remote PC)

**Configuration:**
- LiDAR -> Jetson: `192.168.123.164` (wired Ethernet)
- Jetson -> Remote PC: Wi-Fi or separate Ethernet
- SLAM runs on Jetson, viewer on Remote PC

**Setup:**
```bash
# On Jetson (transmitter)
cd /home/unitree/AIM-Robotics/SLAM/lidar_tx
./build/lidar_stream config.json 127.0.0.1 9999

# On Jetson (receiver with streaming)
cd /home/unitree/AIM-Robotics/SLAM/slam_rx
python3 live_slam.py \
    --frame-rate 10 \
    --listen-port 9999 \
    --stream-enable \
    --stream-port 7609

# On Remote PC (viewer)
# Replace 192.168.123.164 with Jetson's IP on shared network
python3 viewer_realtime.py \
    --server-ip 192.168.123.164 \
    --port 7609 \
    --flip-y --flip-z
```

**Firewall:**
```bash
# On Jetson, allow ZMQ streaming
sudo ufw allow 7609/tcp
```

---

## Common Issues

### "No packets received"

**Cause:** Transmitter not running or network misconfiguration

**Solution:**
```bash
# 1. Check transmitter is running
ps aux | grep lidar_stream

# 2. Verify LiDAR connectivity
ping 192.168.123.120

# 3. Check network interface
ifconfig eth0  # Should show 192.168.123.x

# 4. Restart transmitter
cd /home/unitree/AIM-Robotics/SLAM/lidar_tx
./build/lidar_stream config.json 127.0.0.1 9999
```

---

### "ModuleNotFoundError: lidar_protocol_cpp"

**Cause:** C++ modules not built

**Solution:**
```bash
cd /home/unitree/AIM-Robotics/SLAM/slam_rx

# Full rebuild
./build.sh clean

# Verify .so files exist
ls -lh *.so
```

---

### "Build failed: pybind11 not found"

**Cause:** Missing pybind11 dependency

**Solution:**
```bash
# Install pybind11
sudo apt-get install python3-pybind11

# Or via pip
pip3 install pybind11
```

---

### "Frames skipped (low point count)"

**Cause:** Too few points after filtering

**Solution:**
```bash
# Option 1: Lower min_points_per_frame
python3 live_slam.py --min-points-per-frame 500 --listen-port 9999

# Option 2: Increase max range
python3 live_slam.py --max-range 30.0 --listen-port 9999

# Option 3: Reduce self-filter radius
python3 live_slam.py --self-filter-radius 0.2 --listen-port 9999
```

---

## Performance Benchmarks

### C++ vs Python Comparison

**Test Environment:**
- Hardware: Jetson Orin NX (ARM64)
- LiDAR: Livox Mid-360 (~2000 pps, 10 Hz framing)
- Compiler: GCC 9.4.0 with -O3 -march=armv8-a+crc

**Results:**

| Phase | Python | C++ | Speedup |
|-------|--------|-----|---------|
| **Phase 1 (Protocol)** | 20.67 ms/frame | 7.68 ms/frame | **2.69x** |
| **Phase 2 (Frame)** | 5.16 ms/frame | 3.25 ms/frame | **1.59x** |
| **Phase 3 (SLAM)** | 29.13 ms/frame | 29.13 ms/frame | 1.0x (already C++) |
| **Total** | **54.96 ms/frame** | **40.06 ms/frame** | **1.37x** |

**Benefits:**
- CPU usage reduced by ~15% (more headroom for other tasks)
- Total processing time reduced by 27% (14.9 ms saved per frame)
- Battery life improved
- Real-time performance margin: 10Hz @ 40ms/frame = 40% CPU utilization

---

## Advanced Usage

### Outdoor Mapping (Long Range)

```bash
# Transmitter: 100m range, 3x downsampling
./build/lidar_stream config.json 127.0.0.1 9999 \
    --max-range 100.0 \
    --downsample 3

# Receiver: Outdoor preset, coarser voxels
python3 live_slam.py \
    --frame-rate 5 \
    --max-range 100.0 \
    --voxel-size 1.0 \
    --preset outdoor \
    --listen-port 9999
```

---

### High-Speed Mapping (Dense)

```bash
# Transmitter: No downsampling
./build/lidar_stream config.json 127.0.0.1 9999 --max-range 15.0

# Receiver: Higher frame rate, finer voxels
python3 live_slam.py \
    --frame-rate 20 \
    --max-range 15.0 \
    --voxel-size 0.1 \
    --min-points-per-frame 1200 \
    --listen-port 9999
```

---

## License

Part of AIM-Robotics project.

---

## Authors

AIM Robotics Team - 2025-11-03
