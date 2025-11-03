# AIM-Robotics

Unitree G1 robot development examples and utilities

---

## Project Structure

```
AIM-Robotics/
├── SLAM/               # LiDAR SLAM system (Livox Mid-360 + KISS-ICP)
├── LiDAR/              # LiDAR streaming and visualization
├── RealSense/          # Intel RealSense camera utilities
├── audio/              # Audio recording and processing
├── Light/              # LED control utilities
├── debug_g1_loco.py    # Locomotion debugging utility
└── debug_g1_arm.py     # Arm control debugging utility
```

---

## Component Documentation

- **[SLAM](./SLAM/README.md)** - Complete LiDAR SLAM system with real-time mapping
- **[LiDAR](./LiDAR/README.md)** - LiDAR streaming and 3D visualization
- **[RealSense](./RealSense/README.md)** - RealSense camera integration (if available)

---

## Prerequisites

**Unitree SDK2 Python:**
```bash
git clone https://github.com/unitreerobotics/unitree_sdk2_python.git
cd unitree_sdk2_python
pip3 install -e .
```

---

## Development Environment

- **Platform**: Unitree G1 (Jetson Orin NX)
- **OS**: Ubuntu 20.04 (JetPack 5.x)
- **Python**: 3.8+

---

Made with 💡 by AIM Robotics
