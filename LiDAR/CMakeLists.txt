cmake_minimum_required(VERSION 3.10)
project(g1_lidar_example)

set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Find Livox SDK2 library
find_library(LIVOX_LIDAR_SDK_LIBRARY
    NAMES livox_lidar_sdk_shared
    PATHS /usr/local/lib
)

# Include header files
include_directories(/usr/local/include)

# Streaming program (for visualization)
add_executable(g1_lidar_stream g1_lidar_stream.cpp)
target_link_libraries(g1_lidar_stream ${LIVOX_LIDAR_SDK_LIBRARY})
