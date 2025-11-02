cmake_minimum_required(VERSION 3.10)
project(lidar_stream)

# C++14 standard
set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Build type
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

# Compiler flags
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -Wall -Wextra")
set(CMAKE_CXX_FLAGS_DEBUG "-g -O0")
set(CMAKE_CXX_FLAGS_RELEASE "-O3 -DNDEBUG")

# Find Livox SDK2
find_library(LIVOX_LIDAR_SDK_LIBRARY
    NAMES livox_lidar_sdk_shared
    PATHS /usr/local/lib
    REQUIRED
)

# Include directories
include_directories(
    /usr/local/include
)

# Executable
add_executable(lidar_stream
    lidar_stream.cpp
)

# Link libraries
target_link_libraries(lidar_stream
    ${LIVOX_LIDAR_SDK_LIBRARY}
    pthread
    m
)

# Install target
install(TARGETS lidar_stream
    RUNTIME DESTINATION bin
)

# Print configuration
message(STATUS "Build type: ${CMAKE_BUILD_TYPE}")
message(STATUS "C++ standard: ${CMAKE_CXX_STANDARD}")
message(STATUS "Livox SDK: ${LIVOX_LIDAR_SDK_LIBRARY}")
