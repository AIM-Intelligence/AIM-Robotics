# AIM-Robotics

Unitree G1 robot development examples and utilities

---

## Project Structure

```
AIM-Robotics/
├── SLAM/               # LiDAR SLAM system (Livox Mid-360 + KISS-ICP)
├── LiDAR/              # LiDAR streaming and visualization
├── RealSense/          # Intel RealSense camera utilities
├── YOLOv8n/            # YOLOv8 real-time object detection + streaming
├── audio/              # Audio recording and processing
├── Light/              # LED control utilities
├── debug_g1_loco.py    # Locomotion debugging utility
└── debug_g1_arm.py     # Arm control debugging utility
```

---

## Component Documentation

- **[SLAM](./SLAM/README.md)** - Complete LiDAR SLAM system with real-time mapping
- **[LiDAR](./LiDAR/README.md)** - LiDAR streaming and 3D visualization
- **[RealSense](./RealSense/README.md)** - RealSense camera integration
- **[YOLOv8n](./YOLOv8n/README.md)** - YOLOv8 object detection with RealSense + UDP streaming

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
- **OS**: Ubuntu 20.04 (JetPack 5.1.1 / L4T R35.3.1)
- **Python**: 3.8
- **CUDA**: 11.4

---

## GPU Setup for Deep Learning

**Important**: Standard `pip install torch` installs CPU-only PyTorch. For GPU acceleration on Jetson, use NVIDIA's official wheels.

### Install PyTorch with CUDA Support (JetPack 5.1.x)

```bash
# 1. Remove CPU-only PyTorch if installed
python3 -m pip uninstall -y torch torchvision torchaudio
python3 -m pip cache purge

# 2. Install NVIDIA's PyTorch 2.1.0 for Jetson (CUDA-enabled)
export TORCH_WHL='https://developer.download.nvidia.cn/compute/redist/jp/v512/pytorch/torch-2.1.0a0%2B41361538.nv23.06-cp38-cp38-linux_aarch64.whl'
python3 -m pip install --no-cache-dir "$TORCH_WHL"

# 3. Install torchvision (may show version warning - safe to ignore)
python3 -m pip install --no-cache-dir torchvision

# 4. Reinstall PyTorch to ensure CUDA version is active
python3 -m pip uninstall -y torch
python3 -m pip install --no-cache-dir "$TORCH_WHL"

# 5. Verify GPU is recognized
python3 -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}'); print(f'Device: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"N/A\"}')"
```

**Expected output:**
```
CUDA available: True
Device: Orin
```

### Troubleshooting

**Issue**: `pip install ultralytics` reinstalls CPU PyTorch
- **Solution**: Install PyTorch first, then install ultralytics with `--no-deps` flag

**Issue**: torchvision version mismatch warning
- **Solution**: Safe to ignore for YOLO - works with torch core dependencies only
- **Optional**: Build torchvision 0.16.0 from source for perfect compatibility (30-60 min build time)
  ```bash
  # Only if needed for torchvision.models or advanced features
  git clone https://github.com/pytorch/vision.git && cd vision && git checkout v0.16.0
  export TORCH_CUDA_ARCH_LIST="8.7" FORCE_CUDA=1 MAX_JOBS=4
  python3 -m pip install --no-build-isolation --no-deps -v .
  ```

**References**:
- [NVIDIA PyTorch for Jetson](https://docs.nvidia.com/deeplearning/frameworks/install-pytorch-jetson-platform/index.html)
- [PyTorch for Jetson Forum](https://forums.developer.nvidia.com/t/pytorch-for-jetson/72048)

---

Made with 💡 by AIM Robotics
