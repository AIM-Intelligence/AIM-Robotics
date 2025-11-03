#!/bin/bash
# C++ Module Build Script
# Usage:
#   ./build.sh         # Quick rebuild (only changed files)
#   ./build.sh clean   # Full rebuild (from scratch)

set -e  # Exit on error

SCRIPT_DIR="$(dirname "$0")"
cd "$SCRIPT_DIR/cpp"

if [ "$1" == "clean" ]; then
    echo "========================================"
    echo "Full C++ Build (clean)"
    echo "========================================"

    echo "Cleaning build directory..."
    rm -rf build
    mkdir build
    cd build

    echo ""
    echo "Running CMake..."
    cmake ..

    echo ""
    echo "Compiling..."
    make -j$(nproc)
else
    echo "========================================"
    echo "Quick Rebuild"
    echo "========================================"

    if [ ! -d "build" ]; then
        echo "Build directory doesn't exist. Running full build..."
        mkdir build
        cd build
        cmake ..
    else
        cd build
    fi

    echo "Compiling (incremental)..."
    make -j$(nproc)
fi

# Copy .so files
echo ""
echo "Copying .so files..."
cp *.so ../../

echo ""
echo "========================================"
echo "✅ Build successful!"
echo "========================================"
echo ""
ls -lh ../../*.so

# Test import
echo ""
echo "Testing modules..."
cd ../..
python3 -c "from lidar_protocol_cpp import LidarProtocol; from frame_builder_cpp import FrameBuilder; print('✅ Both modules work!')"
