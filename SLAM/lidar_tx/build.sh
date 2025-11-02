#!/bin/bash
#
# Build script for LiDAR Stream
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$SCRIPT_DIR/build"

echo "========================================"
echo "Building LiDAR Stream"
echo "========================================"

# Create build directory
if [ ! -d "$BUILD_DIR" ]; then
    echo "Creating build directory..."
    mkdir -p "$BUILD_DIR"
fi

cd "$BUILD_DIR"

# Configure
echo "Running CMake..."
cmake -DCMAKE_BUILD_TYPE=Release ..

# Build
echo "Building..."
make -j$(nproc)

echo ""
echo "✓ Build complete!"
echo ""
echo "Executable: $BUILD_DIR/lidar_stream"
echo ""
echo "Usage:"
echo "  ./build/lidar_stream config.json <ip> <port>"
echo ""
