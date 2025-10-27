cmake_minimum_required(VERSION 3.10)
project(g1_lidar_example)

set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Livox SDK2 라이브러리 찾기
find_library(LIVOX_LIDAR_SDK_LIBRARY
    NAMES livox_lidar_sdk_shared
    PATHS /usr/local/lib
)

# 헤더 파일 경로
include_directories(/usr/local/include)

# 스트리밍 프로그램 (시각화용)
add_executable(g1_lidar_stream g1_lidar_stream.cpp)
target_link_libraries(g1_lidar_stream ${LIVOX_LIDAR_SDK_LIBRARY})
