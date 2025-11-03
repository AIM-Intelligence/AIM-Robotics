# G1 Live SLAM

**Modular LiDAR SLAM Receiver - C++ Optimized Version**

---

## Overview

System for receiving LiDAR Stream protocol and performing KISS-ICP based SLAM.

**Key Features:**
- C++ Optimized Backend (Protocol + Frame Builder)
- Structured packet header parsing (magic, timestamp, sequence, CRC)
- Time-based frame reconstruction (device timestamp)
- Packet loss detection (sequence tracking)
- CRC32 integrity verification
- Modular architecture (protocol → frame → SLAM)
- Stationary stability analysis (drift tracking)

---

## File Structure

```
/home/unitree/AIM-Robotics/SLAM/slam_rx/
├── live_slam.py           # Main entry point
├── slam_pipeline.py       # KISS-ICP wrapper
├── build.sh               # C++ build script
├── cpp/                   # C++ optimized implementation
│   ├── CMakeLists.txt
│   ├── include/
│   │   ├── lidar_protocol_cpp.hpp
│   │   └── frame_builder_cpp.hpp
│   ├── src/
│   │   ├── lidar_protocol_cpp.cpp       # Protocol Parser (Phase 1)
│   │   ├── lidar_protocol_pybind.cpp
│   │   ├── frame_builder_cpp.cpp        # Frame Builder (Phase 2)
│   │   └── frame_builder_pybind.cpp
│   └── build/             # Build output (generated)
├── tests/
│   └── test_protocol.py   # Unit tests
├── lidar_protocol_cpp.so  # Built C++ module
├── frame_builder_cpp.so   # Built C++ module
└── README.md              # This file
```

---

## Quick Start

### 1. Check Dependencies

```bash
# Required packages
pip3 install numpy open3d kiss-icp

# C++ build tools (should already be installed)
# - g++ or clang++
# - cmake
# - python3-dev
# - pybind11
```

### 2. Build C++ Modules

```bash
cd /home/unitree/AIM-Robotics/SLAM/slam_rx

# First build or full rebuild
./build.sh clean

# Quick rebuild (changed files only)
./build.sh
```

**On Successful Build:**
```
========================================
✅ Build successful!
========================================

-rw-rw-r-- 1 unitree unitree 234K Nov  3 10:15 frame_builder_cpp.so
-rw-rw-r-- 1 unitree unitree 198K Nov  3 10:15 lidar_protocol_cpp.so

Testing modules...
✅ Both modules work!
```

### 3. Start LiDAR Transmitter

```bash
cd /home/unitree/AIM-Robotics/SLAM/lidar_tx
./build/lidar_stream config.json 127.0.0.1 9999
```

### 4. Start SLAM Receiver

```bash
cd /home/unitree/AIM-Robotics/SLAM/slam_rx
python3 live_slam.py --frame-rate 10 --max-range 15.0 --listen-port 9999
```

---

## Usage Examples

### Basic Execution (Indoor, 10Hz)

```bash
python3 live_slam.py --frame-rate 10 --max-range 15.0 --listen-port 9999
```

**Expected Output:**
```
======================================================================
G1 Live SLAM
======================================================================
Frame rate:       10 Hz
Range:            0.1 - 15.0 m
Voxel size:       0.15 m
Self-filter:      r=0.3m, z=±0.24m (symmetric)
Min pts/frame:    800
Preset:           indoor (ICP tuning applied)
Debug:            False
======================================================================

✓ UDP socket listening on 0.0.0.0:9999
Listening for LiDAR packets... (Ctrl+C to stop)

======================================================================
[RX] Packets: 1543 (1542.8 pps), Valid: 1543
     Errors: CRC=0, Magic=0, Len=0
[FRAME] Built: 20, Packets: 1543, Avg pts/frame: 7215
        Late: 0, Gaps: 0, Reorder: 0
[SLAM] Processed: 20, Skipped: 0
       Position: [0.12, -0.03, 0.01], Distance: 0.15m
       Map points: 45230
======================================================================
```

### Outdoor SLAM (Low Speed, Long Range)

```bash
python3 live_slam.py \
    --frame-rate 10 \
    --max-range 50.0 \
    --preset outdoor \
    --listen-port 9999
```

### Debug Mode (Detailed Packet/Frame Logs)

```bash
python3 live_slam.py --frame-rate 10 --listen-port 9999 --debug
```

**Debug Output Example:**
```
[PROTO] ✓ Valid packet: seq=42, ts=1000000000, pts=105, crc=0x12345678
[FRAME] ▶ New frame started: ts=1000000000, seq=42
[FRAME] ■ Frame closed: Frame(pts=7215, pkts=72, dur=0.050s, seq=42-113)
[SLAM] ✓ Frame registered: pts=6892, pos=[0.12, -0.03, 0.01], dist=0.15m
```

### Stationary Stability Test (30 seconds)

```bash
# Run after fixing robot in place
python3 live_slam.py --frame-rate 10 --listen-port 9999

# After 30 seconds, press Ctrl+C
```

**Drift Analysis Output on Exit:**
```
======================================================================
POSE DRIFT ANALYSIS (600 samples)
======================================================================
Mean Δt per frame: 0.0085 m
Std deviation:     0.0042 m
Max Δt:            0.0234 m
✅ PASS: Mean drift < 0.02m (stationary stability)
======================================================================
```

---

## Command-Line Options

### Network

| Option | Default | Description |
|--------|---------|-------------|
| `--listen-ip` | `0.0.0.0` | UDP listen IP |
| `--listen-port` | `9999` | UDP listen port |

### Frame Building

| Option | Default | Description |
|--------|---------|-------------|
| `--frame-rate` | `20` | Target frame rate (Hz) |

### Filtering

| Option | Default | Description |
|--------|---------|-------------|
| `--min-range` | `0.1` | Minimum range (m) |
| `--max-range` | `20.0` | Maximum range (m) |
| `--self-filter-radius` | `0.4` | Robot self-filter radius (m) |
| `--self-filter-z-min` | `-0.2` | Robot self-filter Z minimum (m) |
| `--self-filter-z-max` | `0.5` | Robot self-filter Z maximum (m) |

### SLAM

| Option | Default | Description |
|--------|---------|-------------|
| `--voxel-size` | `0.5` | Voxel downsampling size (m) |
| `--min-points-per-frame` | `800` | Minimum points per frame (stability) |
| `--preset` | `indoor` | Preset (`indoor`, `outdoor`, `custom`) |

### Output

| Option | Default | Description |
|--------|---------|-------------|
| `--no-save-map` | `False` | Don't save map on exit |

### Debug

| Option | Default | Description |
|--------|---------|-------------|
| `--debug` | `False` | Enable debug logging |

---

## Unit Tests

```bash
cd /home/unitree/AIM-Robotics/SLAM/slam_rx/tests
python3 test_protocol.py
```

**Expected Output:**
```
======================================================================
LiDAR Protocol  Parser - Unit Tests
======================================================================

======================================================================
TEST 1: Valid packet (CRC disabled)
======================================================================
[PROTO] ✓ Valid packet: seq=42, ts=1000000000, pts=2, crc=0x00000000
✓ Test passed: ProtocolStats(total=1, valid=1, ...)

[... 5 more tests ...]

======================================================================
RESULTS: 6/6 passed, 0 failed
======================================================================
```

---

## Performance (C++ Optimization)

**Measured Results** (Livox Mid-360, 2000 pps, 10 Hz):

| Phase | Python | C++ | Speedup |
|-------|--------|-----|---------|
| **Phase 1 (Protocol)** | 20.67 ms/frame | 7.68 ms/frame | **2.69x** |
| **Phase 2 (Frame)** | 5.16 ms/frame | 3.25 ms/frame | **1.59x** |
| **SLAM (KISS-ICP)** | 29.13 ms/frame | 29.13 ms/frame | Same (already C++) |
| **Total** | **54.96 ms** | **40.06 ms** | **1.37x** |

**Key Benefits:**
- CPU usage reduced by ~15% (more headroom for other tasks)
- Total processing time reduced by 27% (14.9ms saved per frame)
- Battery life improved
- Real-time processing margin: 10Hz @ 40ms/frame = 40% CPU utilization

---

## Performance Tuning

### Adjusting Frame Rate

**Symptom:** Excessive jitter when stationary
**Solution:** Lower frame rate

```bash
# 10Hz → 5Hz
python3 live_slam.py --frame-rate 5 --listen-port 9999
```

### Low Point Frame Skipping

**Symptom:** Unstable in noisy environments
**Solution:** Increase `--min-points-per-frame`

```bash
python3 live_slam.py --frame-rate 10 --min-points-per-frame 1200 --listen-port 9999
```

---

## Acceptance Criteria

### 1. Stationary Stability
- **Condition:** mean(|Δt|) < 0.02m over 30 seconds with robot fixed
- **Verification:** Check "POSE DRIFT ANALYSIS" output on exit

### 2. Frame Rate
- **Condition:** frame_rate ≈ CLI setting (±10%)
- **Verification:** Check frames per second in `[FRAME] Built:` log

### 3. CRC/Parser
- **Condition:** `crc_fail == 0`, `bad_magic == 0`, `len_mismatch == 0`
- **Verification:** All errors == 0 in `[RX] Errors:` log

### 4. Lossless Segments
- **Condition:** `late_packets == 0` (normal network), operates correctly even with `seq_gap`
- **Verification:** Check `[FRAME] Late:` and `Gaps:` logs

### 5. Shutdown
- **Condition:** Map saved without exceptions on Ctrl+C
- **Verification:** `slam_map__YYYYMMDD_HHMMSS.pcd` file created

---

## Troubleshooting

### Problem: "ModuleNotFoundError: No module named 'lidar_protocol_cpp'"

**Cause:** C++ modules not built or .so files missing

**Solution:**
```bash
cd /home/unitree/AIM-Robotics/SLAM/slam_rx

# Full rebuild
./build.sh clean

# Verify .so files
ls -lh *.so
```

### Problem: Build Failure "pybind11 not found"

**Cause:** pybind11 library not installed

**Solution:**
```bash
# Ubuntu/Debian
sudo apt-get install python3-pybind11

# Or install via pip
pip3 install pybind11
```

### Problem: "No packets received"

**Cause:** Transmitter not running or port mismatch

**Solution:**
```bash
# Check transmitter
ps aux | grep lidar_stream

# Restart transmitter
cd /home/unitree/AIM-Robotics/SLAM/lidar_tx
./build/lidar_stream config.json 127.0.0.1 9999
```

### Problem: "CRC failures"

**Cause:** CRC configuration mismatch between transmitter and receiver

**Solution:**
```bash
# Disable CRC in transmitter
./build/lidar_stream config.json 127.0.0.1 9999

# Or disable CRC verification in receiver (modify lidar_protocol.py)
# validate_crc=False
```

### Problem: "Frames skipped (low point count)"

**Cause:** Too few points after filtering

**Solution:**
```bash
# Lower min_points_per_frame
python3 live_slam.py --min-points-per-frame 500 --listen-port 9999

# Or increase range
python3 live_slam.py --max-range 30.0 --listen-port 9999
```

### Problem: "Sequence gaps"

**Cause:** UDP packet loss (network congestion)

**Verification:** Check `Dropped packets` in transmitter logs

**Solution:**
- Use local network (127.0.0.1)
- Apply `--downsample 2` in transmitter (reduce bandwidth)

---

## ZMQ Real-time Streaming

View real-time map on Mac/remote PC:

```bash
# Jetson (transmit)
python3 live_slam.py \
    --frame-rate 10 \
    --listen-port 9999 \
    --stream-enable \
    --stream-port 7609

# Mac/PC (receive)
python3 viewer_realtime.py \
    --server-ip 192.168.123.164 \
    --port 7609 \
    --flip-y --flip-z
```

---

## System Features

| Feature | Description |
|---------|-------------|
| Packet format | 27B header + points (magic, timestamp, sequence, CRC) |
| Timestamp | Device hardware time (ns precision) |
| Frame reconstruction | Time window based (10Hz = 0.1s periods) |
| Loss detection | Sequence tracking |
| CRC verification | IEEE 802.3 CRC32 |
| Backend | C++ (pybind11 bindings) |
| Build system | CMake + build.sh wrapper |
| Structure | Modular (live_slam.py, slam_pipeline.py, cpp/) |

---

## License

Part of AIM-Robotics project.

---

## Authors

AIM Robotics Team - 2025-11-02
