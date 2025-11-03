#include "lidar_protocol_cpp.hpp"
#include <cstring>
#include <sstream>
#include <iostream>
#include <zlib.h>

#ifdef HAVE_ARM_CRC32
#include <arm_acle.h>
#endif

#ifdef HAVE_SSE42_CRC32
#include <nmmintrin.h>
#endif

// ============================================================================
// ProtocolStats Implementation
// ============================================================================

std::string ProtocolStats::repr() const {
    std::ostringstream oss;
    oss << "ProtocolStats(total=" << total_packets
        << ", valid=" << valid_packets
        << ", crc_fail=" << crc_failures
        << ", bad_magic=" << bad_magic
        << ", bad_ver=" << bad_version
        << ", len_err=" << len_mismatch
        << ", count_err=" << invalid_count << ")";
    return oss.str();
}

// ============================================================================
// LidarProtocol Implementation
// ============================================================================

LidarProtocol::LidarProtocol(bool validate_crc)
    : validate_crc_(validate_crc) {}

#ifdef HAVE_ARM_CRC32
// ARM CRC32 hardware acceleration (ARMv8+)
uint32_t LidarProtocol::crc32_hw_arm(const uint8_t* data, size_t length) {
    uint32_t crc = 0xFFFFFFFF;

    // Process 8 bytes at a time
    size_t i = 0;
    for (; i + 7 < length; i += 8) {
        uint64_t val;
        std::memcpy(&val, data + i, 8);
        crc = __crc32cd(crc, val);
    }

    // Process 4 bytes
    if (i + 3 < length) {
        uint32_t val;
        std::memcpy(&val, data + i, 4);
        crc = __crc32cw(crc, val);
        i += 4;
    }

    // Process 2 bytes
    if (i + 1 < length) {
        uint16_t val;
        std::memcpy(&val, data + i, 2);
        crc = __crc32ch(crc, val);
        i += 2;
    }

    // Process final byte
    if (i < length) {
        crc = __crc32cb(crc, data[i]);
    }

    return crc ^ 0xFFFFFFFF;
}
#endif

#ifdef HAVE_SSE42_CRC32
// x86 SSE4.2 CRC32 hardware acceleration
uint32_t LidarProtocol::crc32_hw_sse42(const uint8_t* data, size_t length) {
    uint32_t crc = 0xFFFFFFFF;

    size_t i = 0;
    for (; i + 7 < length; i += 8) {
        uint64_t val;
        std::memcpy(&val, data + i, 8);
        crc = _mm_crc32_u64(crc, val);
    }

    for (; i + 3 < length; i += 4) {
        uint32_t val;
        std::memcpy(&val, data + i, 4);
        crc = _mm_crc32_u32(crc, val);
    }

    for (; i < length; i++) {
        crc = _mm_crc32_u8(crc, data[i]);
    }

    return crc ^ 0xFFFFFFFF;
}
#endif

// Software fallback using zlib
uint32_t LidarProtocol::crc32_sw_zlib(const uint8_t* data, size_t length) {
    return ::crc32(0, data, length);
}

// Main CRC32 calculation (auto-dispatch to best available method)
uint32_t LidarProtocol::crc32_ieee(const uint8_t* data, size_t length) {
#ifdef HAVE_ARM_CRC32
    return crc32_hw_arm(data, length);
#elif defined(HAVE_SSE42_CRC32)
    return crc32_hw_sse42(data, length);
#else
    return crc32_sw_zlib(data, length);
#endif
}

// Main parsing function
std::optional<ParsedPacket> LidarProtocol::parse_datagram(
    const uint8_t* data,
    size_t length,
    bool debug
) {
    stats_.total_packets++;

    // 1. Length check (minimum: header only)
    if (length < HEADER_SIZE) {
        stats_.len_mismatch++;
        if (debug) {
            std::cerr << "[PROTO] Length too short: " << length
                     << " < " << HEADER_SIZE << std::endl;
        }
        return std::nullopt;
    }

    // 2. Parse header (zero-copy: direct pointer cast)
    const PacketHeader* header = reinterpret_cast<const PacketHeader*>(data);

    // 3. Validate magic
    if (header->magic != LIDAR_MAGIC) {
        stats_.bad_magic++;
        if (debug) {
            std::cerr << "[PROTO] Bad magic: 0x" << std::hex
                     << header->magic << " != 0x" << LIDAR_MAGIC
                     << std::dec << std::endl;
        }
        return std::nullopt;
    }

    // 4. Validate version
    if (header->version != LIDAR_VERSION) {
        stats_.bad_version++;
        if (debug) {
            std::cerr << "[PROTO] Bad version: " << (int)header->version
                     << " != " << (int)LIDAR_VERSION << std::endl;
        }
        return std::nullopt;
    }

    // 5. Validate point count
    if (header->point_count < 1 || header->point_count > MAX_POINTS_PER_PACKET) {
        stats_.invalid_count++;
        if (debug) {
            std::cerr << "[PROTO] Invalid point_count: " << header->point_count
                     << " (valid: 1-" << MAX_POINTS_PER_PACKET << ")" << std::endl;
        }
        return std::nullopt;
    }

    // 6. Validate total length
    size_t expected_len = HEADER_SIZE + header->point_count * POINT_SIZE;
    if (length != expected_len) {
        stats_.len_mismatch++;
        if (debug) {
            std::cerr << "[PROTO] Length mismatch: " << length
                     << " != " << expected_len << " (header=" << HEADER_SIZE
                     << " + " << header->point_count << "×" << POINT_SIZE
                     << ")" << std::endl;
        }
        return std::nullopt;
    }

    // 7. CRC validation (if enabled and CRC != 0)
    if (validate_crc_ && header->crc32 != 0) {
        // CRC over: header[0..22] + payload (excludes CRC field itself at [23..26])
        // Use zlib crc32 for IEEE 802.3 compatibility (NOT ARM CRC32C hardware)
        uint32_t calculated_crc = ::crc32(0, data, 23);  // First 23 bytes

        // Continue with payload after CRC field
        const uint8_t* payload = data + HEADER_SIZE;
        size_t payload_len = header->point_count * POINT_SIZE;
        calculated_crc = ::crc32(calculated_crc, payload, payload_len);

        if (calculated_crc != header->crc32) {
            stats_.crc_failures++;
            if (debug) {
                std::cerr << "[PROTO] CRC mismatch: calculated=0x" << std::hex
                         << calculated_crc << " != received=0x" << header->crc32
                         << std::dec << std::endl;
            }
            return std::nullopt;
        }
    }

    // 8. Parse points (single pass, direct memory access)
    ParsedPacket result;
    result.device_ts_ns = header->device_ts_ns;
    result.seq = header->seq;
    result.point_count = header->point_count;
    result.sensor_id = header->sensor_id;
    result.flags = header->flags;
    result.crc32 = header->crc32;

    // Pre-allocate arrays
    size_t n_points = header->point_count;
    result.points_data.reserve(n_points * 4);  // x, y, z, intensity
    result.xyz_data.reserve(n_points * 3);     // x, y, z only

    // Zero-copy point parsing
    const Point* points = reinterpret_cast<const Point*>(data + HEADER_SIZE);

    for (size_t i = 0; i < n_points; i++) {
        const Point& pt = points[i];

        // points array: (N, 4)
        result.points_data.push_back(pt.x);
        result.points_data.push_back(pt.y);
        result.points_data.push_back(pt.z);
        result.points_data.push_back(static_cast<float>(pt.intensity));

        // xyz array: (N, 3)
        result.xyz_data.push_back(pt.x);
        result.xyz_data.push_back(pt.y);
        result.xyz_data.push_back(pt.z);
    }

    stats_.valid_packets++;

    if (debug) {
        std::cout << "[PROTO] ✓ Valid packet: seq=" << result.seq
                 << ", ts=" << result.device_ts_ns
                 << ", pts=" << result.point_count
                 << ", crc=0x" << std::hex << result.crc32 << std::dec
                 << std::endl;
    }

    return result;
}
