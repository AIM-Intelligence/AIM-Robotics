# G1 Live SLAM (Python Implementation)

**Pure Python Implementation - Reference Archive**

---

## Note

This directory is a **Python implementation backup**.
For production use, the **C++ optimized version** is recommended:
👉 `/home/unitree/AIM-Robotics/SLAM/slam_rx/`

**Performance Comparison:**
- Python: ~55 ms/frame
- C++ optimized: ~40 ms/frame (27% faster, 15% CPU reduction)

---

## File Structure

```
slam_rx_python/
├── live_slam.py           # Main entry point
├── lidar_protocol.py      # Packet parser (Python)
├── frame_builder.py       # Frame builder (Python)
├── slam_pipeline.py       # KISS-ICP wrapper
└── README.md              # This file
```

---

## Quick Start

### 1. Start LiDAR Transmitter

```bash
cd /home/unitree/AIM-Robotics/SLAM/lidar_tx
./build/lidar_stream config.json 127.0.0.1 9999
```

### 2. Start SLAM Receiver (Python Version)

```bash
cd /home/unitree/AIM-Robotics/SLAM/slam_rx_python
python3 live_slam.py --frame-rate 10 --listen-port 9999
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

## Why Keep This?

1. **Reference Implementation**: For comparison/verification with C++ implementation
2. **Debugging**: Python is easier in some cases
3. **Education/Learning**: Simpler code for understanding algorithms

---

**For production use, the C++ version is recommended**
👉 `/home/unitree/AIM-Robotics/SLAM/slam_rx/README.md`

---

AIM Robotics Team - 2025-11-03
