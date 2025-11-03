#pragma once

#include <cstdint>
#include <vector>
#include <string>
#include <optional>

// Protocol constants
constexpr uint32_t LIDAR_MAGIC = 0x4C495652;  // "LIVR"
constexpr uint8_t LIDAR_VERSION = 1;
constexpr size_t HEADER_SIZE = 27;
constexpr size_t POINT_SIZE = 13;
constexpr size_t MAX_POINTS_PER_PACKET = 105;

// Packed header structure (little-endian)
#pragma pack(push, 1)
struct PacketHeader {
    uint32_t magic;         // 0x4C495652 ("LIVR")
    uint8_t version;        // 1
    uint64_t device_ts_ns;  // nanoseconds
    uint32_t seq;           // sequence number
    uint16_t point_count;   // 1-105
    uint16_t flags;         // reserved
    uint16_t sensor_id;     // sensor ID
    uint32_t crc32;         // IEEE 802.3 checksum
};
#pragma pack(pop)

static_assert(sizeof(PacketHeader) == HEADER_SIZE, "Header must be 27 bytes");

// Point structure (13 bytes: 3 floats + 1 byte)
#pragma pack(push, 1)
struct Point {
    float x, y, z;
    uint8_t intensity;
};
#pragma pack(pop)

static_assert(sizeof(Point) == POINT_SIZE, "Point must be 13 bytes");

// Statistics tracking
class ProtocolStats {
public:
    int total_packets = 0;
    int valid_packets = 0;
    int crc_failures = 0;
    int bad_magic = 0;
    int bad_version = 0;
    int len_mismatch = 0;
    int invalid_count = 0;

    void reset() {
        total_packets = valid_packets = crc_failures = 0;
        bad_magic = bad_version = len_mismatch = invalid_count = 0;
    }

    std::string repr() const;
};

// Parsed packet result
struct ParsedPacket {
    uint64_t device_ts_ns;
    uint32_t seq;
    uint16_t point_count;
    uint16_t sensor_id;
    uint16_t flags;
    uint32_t crc32;

    // points: (N, 4) - x, y, z, intensity
    std::vector<float> points_data;

    // xyz: (N, 3) - x, y, z only
    std::vector<float> xyz_data;
};

// Main parser class
class LidarProtocol {
public:
    explicit LidarProtocol(bool validate_crc = true);

    // Parse datagram (returns nullptr if invalid)
    std::optional<ParsedPacket> parse_datagram(
        const uint8_t* data,
        size_t length,
        bool debug = false
    );

    // CRC32 IEEE 802.3 calculation
    uint32_t crc32_ieee(const uint8_t* data, size_t length);

    // Get statistics
    const ProtocolStats& stats() const { return stats_; }
    ProtocolStats& stats() { return stats_; }

private:
    bool validate_crc_;
    ProtocolStats stats_;

    // Hardware-accelerated CRC (if available)
#ifdef HAVE_ARM_CRC32
    uint32_t crc32_hw_arm(const uint8_t* data, size_t length);
#endif
#ifdef HAVE_SSE42_CRC32
    uint32_t crc32_hw_sse42(const uint8_t* data, size_t length);
#endif

    // Software fallback (zlib)
    uint32_t crc32_sw_zlib(const uint8_t* data, size_t length);
};
