#!/bin/bash
# G1 LiDAR build script

echo "Building G1 LiDAR example..."

# Create build directory
mkdir -p build
cd build

# Run CMake
cmake ..

# Compile
make

if [ $? -eq 0 ]; then
    echo ""
    echo "✓ Build successful!"
    echo ""
    echo "Usage:"
    echo "  ./build/g1_lidar_stream g1_mid360_config.json <VIEWER_IP> <PORT>"
    echo ""
    echo "Example:"
    echo "  ./build/g1_lidar_stream g1_mid360_config.json 10.40.100.105 8888"
else
    echo ""
    echo "✗ Build failed"
    exit 1
fi
