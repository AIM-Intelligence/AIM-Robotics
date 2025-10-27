#!/bin/bash
# G1 LiDAR 예제 빌드 스크립트

echo "G1 LiDAR 예제 빌드 중..."

# 빌드 디렉토리 생성
mkdir -p build
cd build

# CMake 실행
cmake ..

# 컴파일
make

if [ $? -eq 0 ]; then
    echo ""
    echo "✓ 빌드 성공!"
    echo ""
    echo "실행 방법:"
    echo "  ./build/g1_lidar_stream g1_mid360_config.json <맥_IP> <포트>"
    echo ""
    echo "예시:"
    echo "  ./build/g1_lidar_stream g1_mid360_config.json 10.40.100.105 8888"
else
    echo ""
    echo "✗ 빌드 실패"
    exit 1
fi
