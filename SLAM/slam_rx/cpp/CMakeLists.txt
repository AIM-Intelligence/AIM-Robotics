cmake_minimum_required(VERSION 3.18)
project(slam_rx_cpp LANGUAGES CXX)

# C++17 standard
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

# Find Python
find_package(Python3 COMPONENTS Interpreter Development REQUIRED)

# Find pybind11
find_package(pybind11 CONFIG QUIET)
if(NOT pybind11_FOUND)
    # Fallback: try pip installation
    execute_process(
        COMMAND ${Python3_EXECUTABLE} -m pybind11 --cmakedir
        OUTPUT_VARIABLE pybind11_DIR
        OUTPUT_STRIP_TRAILING_WHITESPACE
        RESULT_VARIABLE pybind11_NOTFOUND
    )
    if(pybind11_NOTFOUND EQUAL 0)
        find_package(pybind11 CONFIG REQUIRED)
    else()
        message(FATAL_ERROR "pybind11 not found. Install: pip3 install pybind11")
    endif()
endif()

# Find zlib for CRC32 fallback
find_package(ZLIB REQUIRED)

# Compiler-specific optimizations
if(CMAKE_SYSTEM_PROCESSOR MATCHES "aarch64|arm64")
    message(STATUS "Detected ARM64/aarch64 processor")
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -march=armv8-a+crc")
    add_compile_definitions(HAVE_ARM_CRC32)
elseif(CMAKE_SYSTEM_PROCESSOR MATCHES "x86_64|AMD64")
    message(STATUS "Detected x86_64 processor")
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -msse4.2")
    add_compile_definitions(HAVE_SSE42_CRC32)
endif()

# Optimization flags
set(CMAKE_CXX_FLAGS_RELEASE "${CMAKE_CXX_FLAGS_RELEASE} -O3 -DNDEBUG -ffast-math")
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -Wall -Wextra -fvisibility=hidden")

# Include directories
include_directories(
    ${CMAKE_CURRENT_SOURCE_DIR}/include
    ${Python3_INCLUDE_DIRS}
)

# ============================================================================
# Module 1: LiDAR Protocol Parser (Phase 1)
# ============================================================================

set(LIDAR_PROTOCOL_SOURCES
    src/lidar_protocol_cpp.cpp
    src/pybind_module.cpp
)

pybind11_add_module(lidar_protocol_cpp ${LIDAR_PROTOCOL_SOURCES})

target_link_libraries(lidar_protocol_cpp PRIVATE
    ${Python3_LIBRARIES}
    ZLIB::ZLIB
)

set_target_properties(lidar_protocol_cpp PROPERTIES
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/.."
)

# ============================================================================
# Module 2: Frame Builder (Phase 2)
# ============================================================================

set(FRAME_BUILDER_SOURCES
    src/frame_builder_cpp.cpp
    src/frame_builder_pybind.cpp
)

pybind11_add_module(frame_builder_cpp ${FRAME_BUILDER_SOURCES})

target_link_libraries(frame_builder_cpp PRIVATE
    ${Python3_LIBRARIES}
)

set_target_properties(frame_builder_cpp PROPERTIES
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/.."
)

# Print build info
message(STATUS "========================================")
message(STATUS "SLAM RX C++ Modules Configuration")
message(STATUS "========================================")
message(STATUS "Python3:        ${Python3_VERSION}")
message(STATUS "Python Include: ${Python3_INCLUDE_DIRS}")
message(STATUS "pybind11:       ${pybind11_VERSION}")
message(STATUS "zlib:           ${ZLIB_VERSION_STRING}")
message(STATUS "Processor:      ${CMAKE_SYSTEM_PROCESSOR}")
message(STATUS "Build Type:     ${CMAKE_BUILD_TYPE}")
message(STATUS "CXX Flags:      ${CMAKE_CXX_FLAGS}")
message(STATUS "")
message(STATUS "Modules:")
message(STATUS "  - lidar_protocol_cpp.so (Phase 1)")
message(STATUS "  - frame_builder_cpp.so  (Phase 2)")
message(STATUS "Output Dir:     ${CMAKE_CURRENT_SOURCE_DIR}/..")
message(STATUS "========================================")
