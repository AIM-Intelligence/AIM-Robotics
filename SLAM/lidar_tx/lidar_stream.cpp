/**
 * G1 LiDAR Stream - SLAM-ready Protocol (Enhanced)
 *
 * Features:
 *  - Device timestamp propagation (Livox hardware timestamp)
 *  - Segmentation (multi-packet for large point clouds)
 *  - CRC32 IEEE 802.3 integrity check
 *  - Atomic sequence counter
 *  - Size/endianness guards
 *  - Comprehensive statistics
 *
 * Protocol: See PROTOCOL.md
 *
 * Build:
 *   ./build.sh
 *
 * Usage:
 *   ./build/lidar_stream config.json <target_ip> <port> [--crc] [--max-range 15.0]
 */

#include "livox_lidar_def.h"
#include "livox_lidar_api.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <unistd.h>
#include <arpa/inet.h>
#include <sys/socket.h>
#include <signal.h>
#include <time.h>
#include <math.h>
#include <errno.h>
#include <atomic>

// ============================================
// Configuration
// ============================================

// Protocol constants
#define PROTOCOL_MAGIC 0x4C495652  // "LIVR" in little-endian
#define PROTOCOL_VERSION 1

// MTU safety
#define MAX_UDP_PAYLOAD 1400       // Safe UDP payload size (1500 MTU - headers)
#define HEADER_SIZE 27             // PacketHeader size
#define POINT_SIZE 13              // Point3D size (x,y,z float + intensity uint8)
#define MAX_POINTS_PER_PACKET ((MAX_UDP_PAYLOAD - HEADER_SIZE) / POINT_SIZE)  // 105 points

// Distance gating (meters) - defaults
#define MIN_RANGE 0.1f
#define MAX_RANGE 20.0f
#define DOWNSAMPLE_FACTOR 1

// Network timeout
#define SEND_TIMEOUT_SEC 0
#define SEND_TIMEOUT_USEC 100000   // 100ms

// Logging
#define LOG_INTERVAL_PACKETS 500
#define STATS_WINDOW_SEC 1.0       // 1 second for rate calculation

// Timestamp tracking
#define TS_HISTORY_SIZE 100

// ============================================
// Compile-time checks
// ============================================

// Note: _Static_assert in C++, will be checked at compile time via struct definition

// ============================================
// Data Structures
// ============================================

/**
 * Packet Header (27 bytes, little-endian)
 */
struct __attribute__((packed)) PacketHeader {
    uint32_t magic;              // 0x4C495652 ("LIVR")
    uint8_t  version;            // Protocol version (1)
    uint64_t device_timestamp;   // Device time in nanoseconds (Livox monotonic)
    uint32_t seq;                // Sequence number (wraps at 2^32)
    uint16_t point_count;        // Number of points in this packet
    uint16_t flags;              // Reserved for future use
    uint16_t sensor_id;          // Sensor identifier (0 = primary)
    uint32_t crc32;              // CRC32 of (header[0..22] + payload)
};

// Compile-time size check
static_assert(sizeof(PacketHeader) == 27, "PacketHeader must be exactly 27 bytes");

/**
 * Point3D (13 bytes, little-endian)
 */
struct __attribute__((packed)) Point3D {
    float x;                     // X coordinate (meters)
    float y;                     // Y coordinate (meters)
    float z;                     // Z coordinate (meters)
    uint8_t intensity;           // Reflectivity (0-255)
};

// ============================================
// Global State
// ============================================

// Network
int udp_socket = -1;
struct sockaddr_in target_addr;

// Sequence counter (atomic)
std::atomic<uint32_t> packet_seq(0);

// Statistics (extended)
std::atomic<uint64_t> stats_tx_packets(0);
std::atomic<uint64_t> stats_tx_points(0);
std::atomic<uint64_t> stats_tx_bytes(0);
std::atomic<uint64_t> stats_dropped_packets(0);
std::atomic<uint64_t> stats_filtered_points(0);
std::atomic<uint64_t> stats_segmented_packets(0);
std::atomic<uint64_t> stats_points_segmented(0);
std::atomic<uint64_t> stats_points_dropped_cap(0);
std::atomic<uint64_t> stats_send_eagain(0);
std::atomic<uint32_t> stats_seq_wraps(0);
std::atomic<uint64_t> stats_callback_count(0);

// Timestamp tracking (for validation)
uint64_t ts_history[TS_HISTORY_SIZE];
int ts_history_idx = 0;
uint64_t ts_last = 0;
bool ts_using_fallback = false;
bool ts_first_packet = true;

// Sequence tracking
uint32_t prev_seq = 0;
bool seq_initialized = false;

// Rate calculation
uint64_t rate_last_time = 0;
uint64_t rate_last_packets = 0;
uint64_t rate_last_bytes = 0;

// Graceful shutdown
volatile sig_atomic_t keep_running = 1;

// Config
float g_min_range = MIN_RANGE;
float g_max_range = MAX_RANGE;
int g_downsample = DOWNSAMPLE_FACTOR;
bool g_crc_enabled = false;
bool g_debug = false;

// ============================================
// CRC32 IEEE 802.3
// ============================================

/**
 * CRC32 lookup table (IEEE 802.3 polynomial: 0x04C11DB7)
 */
static uint32_t crc32_table[256];
static bool crc32_table_initialized = false;

void crc32_init_table() {
    for (uint32_t i = 0; i < 256; i++) {
        uint32_t crc = i;
        for (int j = 0; j < 8; j++) {
            if (crc & 1) {
                crc = (crc >> 1) ^ 0xEDB88320;  // Reflected polynomial
            } else {
                crc >>= 1;
            }
        }
        crc32_table[i] = crc;
    }
    crc32_table_initialized = true;
}

/**
 * Calculate CRC32 (IEEE 802.3)
 *
 * @param data Input data
 * @param length Data length
 * @return CRC32 checksum
 */
uint32_t crc32_calculate(const uint8_t* data, size_t length) {
    if (!crc32_table_initialized) {
        crc32_init_table();
    }

    uint32_t crc = 0xFFFFFFFF;  // Initial value
    for (size_t i = 0; i < length; i++) {
        uint8_t index = (crc ^ data[i]) & 0xFF;
        crc = (crc >> 8) ^ crc32_table[index];
    }
    return crc ^ 0xFFFFFFFF;  // Final XOR
}

/**
 * CRC32 Self-Test with IEEE 802.3 Test Vectors
 *
 * Test vectors from IEEE 802.3 specification:
 * - "123456789" → 0xCBF43926
 * - Empty string → 0x00000000
 * - "The quick brown fox jumps over the lazy dog" → 0x414FA339
 */
bool crc32_self_test() {
    bool all_passed = true;

    // Test 1: "123456789" (standard IEEE 802.3 test vector)
    const uint8_t test1[] = {'1', '2', '3', '4', '5', '6', '7', '8', '9'};
    uint32_t crc1 = crc32_calculate(test1, 9);
    bool pass1 = (crc1 == 0xCBF43926);
    if (!pass1) {
        fprintf(stderr, "❌ CRC32 Test 1 FAILED: Expected 0xCBF43926, got 0x%08X\n", crc1);
        all_passed = false;
    }

    // Test 2: Empty data (should yield 0x00000000 after initial/final XOR cancellation)
    uint32_t crc2 = crc32_calculate(nullptr, 0);
    bool pass2 = (crc2 == 0x00000000);
    if (!pass2) {
        fprintf(stderr, "❌ CRC32 Test 2 FAILED: Expected 0x00000000, got 0x%08X\n", crc2);
        all_passed = false;
    }

    // Test 3: "The quick brown fox jumps over the lazy dog"
    const uint8_t test3[] = "The quick brown fox jumps over the lazy dog";
    uint32_t crc3 = crc32_calculate(test3, 43);  // 43 chars (excluding null terminator)
    bool pass3 = (crc3 == 0x414FA339);
    if (!pass3) {
        fprintf(stderr, "❌ CRC32 Test 3 FAILED: Expected 0x414FA339, got 0x%08X\n", crc3);
        all_passed = false;
    }

    if (all_passed) {
        printf("✅ CRC32 Self-Test: All 3 test vectors passed\n");
        printf("   Test 1 (\"123456789\"): 0x%08X ✓\n", crc1);
        printf("   Test 2 (empty): 0x%08X ✓\n", crc2);
        printf("   Test 3 (fox): 0x%08X ✓\n", crc3);
    }

    return all_passed;
}

// ============================================
// Helper Functions
// ============================================

/**
 * Get monotonic timestamp in nanoseconds
 */
uint64_t get_monotonic_ns() {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ULL + (uint64_t)ts.tv_nsec;
}

/**
 * Check if system is little-endian
 */
bool is_little_endian() {
    uint16_t test = 0x0001;
    return *((uint8_t*)&test) == 0x01;
}

/**
 * Extract Livox device timestamp from packet
 *
 * Livox timestamp format (from SDK2):
 *  - timestamp: uint8_t[8] nanoseconds (device monotonic time, little-endian)
 *  - time_type: 0=device monotonic, 1=PTP, 2=GPS, 3=PPS
 *
 * @param data Livox packet
 * @param fallback_ts Fallback timestamp if extraction fails
 * @return Device timestamp in nanoseconds
 */
uint64_t extract_livox_timestamp(LivoxLidarEthernetPacket* data, uint64_t fallback_ts) {
    // Parse timestamp from uint8_t[8] array (little-endian)
    uint64_t ts = 0;
    memcpy(&ts, data->timestamp, sizeof(uint64_t));

    // Debug: log time_type on first packet
    if (ts_first_packet && g_debug) {
        printf("[DEBUG] Livox time_type=%u (0=device, 1=PTP, 2=GPS, 3=PPS)\n", data->time_type);
        printf("[DEBUG] First timestamp: %lu ns (%.6f s)\n", ts, ts / 1e9);
    }

    // Accept timestamp if:
    // 1. First packet (no sanity check) OR
    // 2. time_type == 0 (device monotonic preferred) OR
    // 3. Monotonically increasing with reasonable delta

    bool accept = false;

    if (ts_first_packet) {
        // First packet: always accept (no history for sanity check)
        accept = true;
        ts_first_packet = false;

        if (g_debug) {
            printf("[DEBUG] First packet timestamp accepted: %lu ns\n", ts);
        }
    } else {
        // Subsequent packets: sanity check
        if (ts > ts_last) {
            uint64_t delta = ts - ts_last;

            // Reasonable delta: 0 < Δt < 1 second
            if (delta < 1000000000ULL) {
                accept = true;

                if (g_debug && delta > 100000000ULL) {
                    // Log if delta > 100ms (suspicious but not fatal)
                    printf("[DEBUG] Large timestamp delta: %.3f ms\n", delta / 1e6);
                }
            } else {
                // Delta too large
                if (g_debug) {
                    printf("[DEBUG] Timestamp delta too large: %.3f s, rejecting\n", delta / 1e9);
                }
            }
        } else {
            // Non-monotonic
            if (g_debug) {
                printf("[DEBUG] Non-monotonic timestamp: %lu <= %lu, rejecting\n", ts, ts_last);
            }
        }
    }

    if (accept) {
        ts_using_fallback = false;
        return ts;
    }

    // Fallback: use host monotonic time
    if (!ts_using_fallback) {
        fprintf(stderr, "⚠ WARNING: Livox timestamp invalid (time_type=%u, ts=%lu), using host monotonic (fallback)\n",
                data->time_type, ts);
        ts_using_fallback = true;
    }
    return fallback_ts;
}

/**
 * Update timestamp statistics
 */
void update_ts_stats(uint64_t ts) {
    if (ts_last > 0) {
        uint64_t delta = ts - ts_last;
        ts_history[ts_history_idx] = delta;
        ts_history_idx = (ts_history_idx + 1) % TS_HISTORY_SIZE;

        // Debug: log timestamp delta every 100 packets
        if (g_debug && (stats_callback_count % 100 == 0)) {
            printf("[DEBUG] Timestamp delta: %.3f ms (ts=%lu ns)\n",
                   delta / 1000000.0, ts);
        }
    }
    ts_last = ts;
}

/**
 * Calculate timestamp statistics (mean, stddev)
 */
void calc_ts_stats(double* mean_ms, double* stddev_ms) {
    if (ts_history_idx == 0 && ts_history[0] == 0) {
        *mean_ms = 0.0;
        *stddev_ms = 0.0;
        return;
    }

    // Calculate mean
    double sum = 0.0;
    int count = 0;
    for (int i = 0; i < TS_HISTORY_SIZE; i++) {
        if (ts_history[i] > 0) {
            sum += ts_history[i] / 1000000.0;  // Convert to ms
            count++;
        }
    }
    *mean_ms = (count > 0) ? (sum / count) : 0.0;

    // Calculate stddev
    if (count > 1) {
        double var_sum = 0.0;
        for (int i = 0; i < TS_HISTORY_SIZE; i++) {
            if (ts_history[i] > 0) {
                double delta_ms = ts_history[i] / 1000000.0;
                var_sum += (delta_ms - *mean_ms) * (delta_ms - *mean_ms);
            }
        }
        *stddev_ms = sqrt(var_sum / count);
    } else {
        *stddev_ms = 0.0;
    }
}

// ============================================
// Packet Transmission
// ============================================

/**
 * Send a packet with header + points
 *
 * @param device_ts Device timestamp (nanoseconds)
 * @param points Point array
 * @param count Number of points (must be <= MAX_POINTS_PER_PACKET)
 * @return 0 on success, -1 on failure
 */
int send_packet(uint64_t device_ts, Point3D* points, uint16_t count) {
    if (count == 0 || count > MAX_POINTS_PER_PACKET) {
        fprintf(stderr, "⚠ Invalid point count: %u (max %d)\n", count, MAX_POINTS_PER_PACKET);
        return -1;
    }

    // Calculate payload size
    size_t payload_size = HEADER_SIZE + count * POINT_SIZE;
    uint8_t buffer[MAX_UDP_PAYLOAD];

    if (payload_size > MAX_UDP_PAYLOAD) {
        fprintf(stderr, "⚠ Payload too large: %zu > %d\n", payload_size, MAX_UDP_PAYLOAD);
        return -1;
    }

    // Get sequence number (atomic)
    uint32_t seq = packet_seq.fetch_add(1, std::memory_order_relaxed);

    // Check for wrap-around (only if sequence is initialized and wraps from MAX to 0)
    if (seq_initialized && prev_seq == UINT32_MAX && seq == 0) {
        stats_seq_wraps.fetch_add(1, std::memory_order_relaxed);
        if (g_debug) {
            printf("[DEBUG] Sequence wrapped at 2^32 (prev=%u, curr=%u)\n", prev_seq, seq);
        }
    }

    prev_seq = seq;
    seq_initialized = true;

    // Build header
    struct PacketHeader header;
    header.magic = PROTOCOL_MAGIC;
    header.version = PROTOCOL_VERSION;
    header.device_timestamp = device_ts;
    header.seq = seq;
    header.point_count = count;
    header.flags = 0;
    header.sensor_id = 0;
    header.crc32 = 0;  // Will be calculated below if enabled

    // Copy header to buffer (first 23 bytes, excluding CRC)
    memcpy(buffer, &header, HEADER_SIZE - 4);  // Copy up to CRC field

    // Copy points to buffer
    memcpy(buffer + HEADER_SIZE, points, count * POINT_SIZE);

    // Calculate CRC if enabled
    if (g_crc_enabled) {
        // CRC over: header[0..22] + payload (excluding CRC field itself)
        // Create temporary buffer without CRC field
        size_t header_part = HEADER_SIZE - 4;  // 23 bytes
        size_t payload_part = count * POINT_SIZE;

        // Allocate temp buffer for CRC calculation
        uint8_t* crc_buf = (uint8_t*)malloc(header_part + payload_part);
        memcpy(crc_buf, buffer, header_part);  // Copy header[0..22]
        memcpy(crc_buf + header_part, buffer + HEADER_SIZE, payload_part);  // Copy points

        uint32_t crc = crc32_calculate(crc_buf, header_part + payload_part);
        free(crc_buf);

        header.crc32 = crc;

        // Copy CRC to buffer
        memcpy(buffer + (HEADER_SIZE - 4), &crc, 4);
    } else {
        // CRC disabled: set to 0
        uint32_t zero = 0;
        memcpy(buffer + (HEADER_SIZE - 4), &zero, 4);
    }

    // Send UDP packet
    ssize_t sent = sendto(udp_socket, buffer, payload_size, 0,
                          (struct sockaddr*)&target_addr, sizeof(target_addr));

    if (sent < 0) {
        if (errno == EAGAIN || errno == EWOULDBLOCK) {
            stats_dropped_packets.fetch_add(1, std::memory_order_relaxed);
            stats_send_eagain.fetch_add(1, std::memory_order_relaxed);
            return -1;  // Buffer full
        }
        perror("sendto failed");
        return -1;
    }

    if ((size_t)sent != payload_size) {
        fprintf(stderr, "⚠ Partial send: %zd / %zu bytes\n", sent, payload_size);
        return -1;
    }

    // Update stats (atomic)
    stats_tx_packets.fetch_add(1, std::memory_order_relaxed);
    stats_tx_points.fetch_add(count, std::memory_order_relaxed);
    stats_tx_bytes.fetch_add(payload_size, std::memory_order_relaxed);

    return 0;
}

/**
 * Send point cloud with segmentation
 *
 * Splits large point clouds into multiple packets (MAX_POINTS_PER_PACKET each)
 *
 * @param device_ts Device timestamp
 * @param points Point array
 * @param total_count Total number of points
 * @return Number of packets sent, -1 on error
 */
int send_segmented(uint64_t device_ts, Point3D* points, int total_count) {
    if (total_count <= 0) {
        return 0;
    }

    int packets_sent = 0;
    int remaining = total_count;
    int offset = 0;

    while (remaining > 0) {
        int batch_size = (remaining > MAX_POINTS_PER_PACKET) ? MAX_POINTS_PER_PACKET : remaining;

        if (send_packet(device_ts, points + offset, batch_size) == 0) {
            packets_sent++;
            if (total_count > MAX_POINTS_PER_PACKET) {
                // This is a segmented packet
                stats_segmented_packets.fetch_add(1, std::memory_order_relaxed);
                stats_points_segmented.fetch_add(batch_size, std::memory_order_relaxed);
            }
        } else {
            // Send failed
            stats_points_dropped_cap.fetch_add(remaining, std::memory_order_relaxed);
            fprintf(stderr, "⚠ Segmentation failed: dropped %d points\n", remaining);
            return -1;
        }

        offset += batch_size;
        remaining -= batch_size;
    }

    return packets_sent;
}

// ============================================
// LiDAR Callbacks
// ============================================

/**
 * Point cloud callback from Livox SDK
 */
void PointCloudCallback(uint32_t handle, const uint8_t dev_type,
                        LivoxLidarEthernetPacket* data, void* client_data) {
    (void)handle;
    (void)dev_type;
    (void)client_data;

    // Early exit if shutting down
    if (!keep_running) {
        return;
    }

    if (data == nullptr) return;

    // Process only Cartesian coordinate data
    if (data->data_type != kLivoxLidarCartesianCoordinateHighData) {
        return;
    }

    LivoxLidarCartesianHighRawPoint* raw_points =
        (LivoxLidarCartesianHighRawPoint*)data->data;

    // Extract device timestamp (with fallback)
    uint64_t fallback_ts = get_monotonic_ns();
    uint64_t device_ts = extract_livox_timestamp(data, fallback_ts);
    update_ts_stats(device_ts);

    // Allocate buffer for filtered points (large enough for segmentation)
    const int MAX_FILTERED = 2048;  // Support up to 2048 points per callback
    static Point3D filtered[MAX_FILTERED];
    int filtered_count = 0;

    float min2 = g_min_range * g_min_range;
    float max2 = g_max_range * g_max_range;

    // Filter and convert points
    int skipped_overflow = 0;
    for (int i = 0; i < data->dot_num; i++) {
        // Check buffer overflow (should never happen with 2048 buffer)
        if (filtered_count >= MAX_FILTERED) {
            skipped_overflow++;
            continue;
        }

        // Skip invalid (0,0,0) points
        if (raw_points[i].x == 0 && raw_points[i].y == 0 && raw_points[i].z == 0) {
            stats_filtered_points.fetch_add(1, std::memory_order_relaxed);
            continue;
        }

        // Convert mm to meters
        float x = raw_points[i].x / 1000.0f;
        float y = raw_points[i].y / 1000.0f;
        float z = raw_points[i].z / 1000.0f;

        // Distance gating
        float d2 = x*x + y*y + z*z;
        if (d2 < min2 || d2 > max2) {
            stats_filtered_points.fetch_add(1, std::memory_order_relaxed);
            continue;
        }

        // Downsampling
        if (g_downsample > 1 && (i % g_downsample) != 0) {
            stats_filtered_points.fetch_add(1, std::memory_order_relaxed);
            continue;
        }

        // Add to buffer
        filtered[filtered_count].x = x;
        filtered[filtered_count].y = y;
        filtered[filtered_count].z = z;
        filtered[filtered_count].intensity = raw_points[i].reflectivity;
        filtered_count++;
    }

    // Warn about buffer overflow (should never happen)
    if (skipped_overflow > 0) {
        fprintf(stderr, "⚠ WARNING: Filter buffer overflow! Skipped %d points (buffer size: %d)\n",
                skipped_overflow, MAX_FILTERED);
        stats_points_dropped_cap.fetch_add(skipped_overflow, std::memory_order_relaxed);
    }

    // Send with segmentation
    if (filtered_count > 0) {
        send_segmented(device_ts, filtered, filtered_count);
    }

    // Periodic logging
    stats_callback_count.fetch_add(1, std::memory_order_relaxed);
    uint64_t cb_count = stats_callback_count.load(std::memory_order_relaxed);

    if (cb_count % LOG_INTERVAL_PACKETS == 0) {
        // Calculate rates
        uint64_t now = get_monotonic_ns();
        double elapsed = (now - rate_last_time) / 1e9;  // seconds

        if (elapsed >= STATS_WINDOW_SEC && rate_last_time > 0) {
            uint64_t pkts = stats_tx_packets.load(std::memory_order_relaxed);
            uint64_t bytes = stats_tx_bytes.load(std::memory_order_relaxed);

            double pps = (pkts - rate_last_packets) / elapsed;
            double mbps = ((bytes - rate_last_bytes) * 8.0) / elapsed / 1e6;

            printf("✓ CB #%lu: TX %lu pkts (%lu pts, %.1f pps, %.2f Mbit/s), "
                   "Drop %lu, EAGAIN %lu, Seg %lu, Filt %lu\n",
                   cb_count,
                   pkts,
                   stats_tx_points.load(std::memory_order_relaxed),
                   pps,
                   mbps,
                   stats_dropped_packets.load(std::memory_order_relaxed),
                   stats_send_eagain.load(std::memory_order_relaxed),
                   stats_segmented_packets.load(std::memory_order_relaxed),
                   stats_filtered_points.load(std::memory_order_relaxed));

            rate_last_packets = pkts;
            rate_last_bytes = bytes;
            rate_last_time = now;
        } else if (rate_last_time == 0) {
            // Initialize
            rate_last_time = now;
            rate_last_packets = stats_tx_packets.load(std::memory_order_relaxed);
            rate_last_bytes = stats_tx_bytes.load(std::memory_order_relaxed);

            printf("✓ CB #%lu: TX %lu pkts (%lu pts), Drop %lu, Filt %lu\n",
                   cb_count,
                   stats_tx_packets.load(std::memory_order_relaxed),
                   stats_tx_points.load(std::memory_order_relaxed),
                   stats_dropped_packets.load(std::memory_order_relaxed),
                   stats_filtered_points.load(std::memory_order_relaxed));
        }
    }
}

/**
 * Work mode callback
 */
void WorkModeCallback(livox_status status, uint32_t handle,
                      LivoxLidarAsyncControlResponse* response, void* client_data) {
    (void)handle;
    (void)client_data;

    if (response == nullptr) return;

    if (status == 0 && response->ret_code == 0) {
        printf("✓ LiDAR work mode set to NORMAL\n\n");
    } else {
        printf("⚠ WARNING: Work mode status=%u, ret_code=%u\n", status, response->ret_code);
    }
}

/**
 * LiDAR info change callback
 */
void LidarInfoChangeCallback(const uint32_t handle, const LivoxLidarInfo* info, void* client_data) {
    (void)client_data;

    if (info == nullptr) return;

    printf("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n");
    printf("📡 LiDAR Connected\n");
    printf("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n");
    printf("Serial Number: %s\n", info->sn);
    printf("IP Address:    %s\n", inet_ntoa(*(struct in_addr*)&info->lidar_ip));
    printf("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n");

    SetLivoxLidarWorkMode(handle, kLivoxLidarNormal, WorkModeCallback, nullptr);
    printf("Requesting point cloud streaming...\n");
}

// ============================================
// Signal Handler
// ============================================

void signal_handler(int signum) {
    (void)signum;

    // Prevent multiple invocations
    static volatile sig_atomic_t shutting_down = 0;
    if (shutting_down) {
        return;
    }
    shutting_down = 1;

    printf("\n\n🛑 Shutting down gracefully...\n");
    keep_running = 0;
}

// ============================================
// Main
// ============================================

void print_usage(const char* prog) {
    printf("Usage: %s <config.json> <target_ip> <target_port> [options]\n", prog);
    printf("\nOptions:\n");
    printf("  --min-range <m>      Minimum distance filter (default: %.1f)\n", MIN_RANGE);
    printf("  --max-range <m>      Maximum distance filter (default: %.1f)\n", MAX_RANGE);
    printf("  --downsample <N>     Downsample factor (default: %d)\n", DOWNSAMPLE_FACTOR);
    printf("  --crc                Enable CRC32 checksums\n");
    printf("  --debug              Enable debug logging\n");
    printf("\nEnvironment:\n");
    printf("  LIDAR_CRC32=1        Enable CRC (same as --crc)\n");
    printf("  LIDAR_DEBUG=1        Enable debug logging\n");
    printf("  LIDAR_MIN_RANGE=<m>  Set min range\n");
    printf("  LIDAR_MAX_RANGE=<m>  Set max range\n");
    printf("  LIDAR_DOWNSAMPLE=<N> Set downsample factor\n");
    printf("\nExample:\n");
    printf("  %s config.json 127.0.0.1 9999 --crc --max-range 15.0\n", prog);
}

int main(int argc, char** argv) {
    // Check endianness
    if (!is_little_endian()) {
        fprintf(stderr, "❌ FATAL: System is not little-endian!\n");
        fprintf(stderr, "This protocol requires little-endian architecture.\n");
        return 1;
    }

    // Parse environment variables
    const char* env_crc = getenv("LIDAR_CRC32");
    const char* env_debug = getenv("LIDAR_DEBUG");
    const char* env_min_range = getenv("LIDAR_MIN_RANGE");
    const char* env_max_range = getenv("LIDAR_MAX_RANGE");
    const char* env_downsample = getenv("LIDAR_DOWNSAMPLE");

    if (env_crc && atoi(env_crc) == 1) g_crc_enabled = true;
    if (env_debug && atoi(env_debug) == 1) g_debug = true;
    if (env_min_range) g_min_range = atof(env_min_range);
    if (env_max_range) g_max_range = atof(env_max_range);
    if (env_downsample) g_downsample = atoi(env_downsample);

    // Parse arguments
    if (argc < 4) {
        print_usage(argv[0]);
        return 1;
    }

    const char* config_file = argv[1];
    const char* target_ip = argv[2];
    int target_port = atoi(argv[3]);

    // Parse optional CLI arguments (override environment)
    for (int i = 4; i < argc; i++) {
        if (strcmp(argv[i], "--min-range") == 0 && i+1 < argc) {
            g_min_range = atof(argv[++i]);
        } else if (strcmp(argv[i], "--max-range") == 0 && i+1 < argc) {
            g_max_range = atof(argv[++i]);
        } else if (strcmp(argv[i], "--downsample") == 0 && i+1 < argc) {
            g_downsample = atoi(argv[++i]);
        } else if (strcmp(argv[i], "--crc") == 0) {
            g_crc_enabled = true;
        } else if (strcmp(argv[i], "--debug") == 0) {
            g_debug = true;
        }
    }

    // Initialize CRC table if enabled
    if (g_crc_enabled) {
        crc32_init_table();

        // Run CRC32 self-test
        printf("========================================\n");
        printf("Running CRC32 Self-Test...\n");
        printf("========================================\n");
        if (!crc32_self_test()) {
            fprintf(stderr, "❌ FATAL: CRC32 self-test failed! Implementation is incorrect.\n");
            return 1;
        }
        printf("\n");
    }

    printf("========================================\n");
    printf("G1 LiDAR Stream (Enhanced)\n");
    printf("========================================\n");
    printf("Protocol:     v%d (magic: 0x%08X)\n", PROTOCOL_VERSION, PROTOCOL_MAGIC);
    printf("Endianness:   Little-endian ✓\n");
    printf("Config:       %s\n", config_file);
    printf("Target:       %s:%d\n", target_ip, target_port);
    printf("Range:        %.1f - %.1f m\n", g_min_range, g_max_range);
    printf("Downsample:   1/%d\n", g_downsample);
    printf("CRC32:        %s\n", g_crc_enabled ? "ENABLED" : "disabled");
    printf("Debug:        %s\n", g_debug ? "ON" : "off");
    printf("MTU:          %d bytes (max %d pts/pkt)\n", MAX_UDP_PAYLOAD, MAX_POINTS_PER_PACKET);
    printf("Header:       %d bytes\n", HEADER_SIZE);
    printf("Point:        %d bytes\n", POINT_SIZE);
    printf("----------------------------------------\n\n");

    // Register signal handlers
    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);

    // Create UDP socket
    udp_socket = socket(AF_INET, SOCK_DGRAM, 0);
    if (udp_socket < 0) {
        perror("❌ Failed to create UDP socket");
        return -1;
    }

    // Set socket timeout
    struct timeval timeout;
    timeout.tv_sec = SEND_TIMEOUT_SEC;
    timeout.tv_usec = SEND_TIMEOUT_USEC;
    if (setsockopt(udp_socket, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout)) < 0) {
        perror("⚠ WARNING: Failed to set SO_SNDTIMEO");
    }

    // Increase send buffer
    int sndbuf = 2 * 1024 * 1024;  // 2MB
    if (setsockopt(udp_socket, SOL_SOCKET, SO_SNDBUF, &sndbuf, sizeof(sndbuf)) < 0) {
        perror("⚠ WARNING: Failed to set SO_SNDBUF");
    }

    // Configure target address
    memset(&target_addr, 0, sizeof(target_addr));
    target_addr.sin_family = AF_INET;
    target_addr.sin_port = htons(target_port);
    if (inet_pton(AF_INET, target_ip, &target_addr.sin_addr) <= 0) {
        fprintf(stderr, "❌ Invalid target IP: %s\n", target_ip);
        close(udp_socket);
        return -1;
    }

    printf("✓ UDP socket created (target: %s:%d)\n", target_ip, target_port);

    // Initialize Livox SDK
    if (!LivoxLidarSdkInit(config_file)) {
        fprintf(stderr, "❌ Livox SDK initialization failed\n");
        close(udp_socket);
        return -1;
    }
    printf("✓ Livox SDK initialized\n");

    // Register callbacks
    SetLivoxLidarInfoChangeCallback(LidarInfoChangeCallback, nullptr);
    SetLivoxLidarPointCloudCallBack(PointCloudCallback, nullptr);

    printf("\n🚀 Streaming started...\n");
    printf("Press Ctrl+C to stop\n\n");

    // Main loop
    while (keep_running) {
        sleep(1);
    }

    // Graceful shutdown sequence
    printf("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n");
    printf("Shutdown Sequence\n");
    printf("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n");

    // Step 1: Stop LiDAR streaming (set to standby mode)
    printf("1. Stopping LiDAR streaming...\n");
    // Note: Livox SDK will handle mode change internally during Uninit

    // Step 2: Wait for pending callbacks to complete
    printf("2. Waiting for pending callbacks...\n");
    sleep(1);  // Give callbacks time to exit

    // Step 3: Uninitialize Livox SDK (stops callbacks)
    printf("3. Uninitializing Livox SDK...\n");
    LivoxLidarSdkUninit();

    // Step 4: Close UDP socket (after callbacks stopped)
    printf("4. Closing UDP socket...\n");
    if (udp_socket >= 0) {
        close(udp_socket);
        udp_socket = -1;
    }

    printf("✓ Shutdown sequence complete\n\n");

    // Final statistics
    printf("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n");
    printf("Final Statistics\n");
    printf("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n");

    uint64_t total_pkts = stats_tx_packets.load(std::memory_order_relaxed);
    uint64_t total_pts = stats_tx_points.load(std::memory_order_relaxed);
    uint64_t total_bytes = stats_tx_bytes.load(std::memory_order_relaxed);
    uint64_t total_cbs = stats_callback_count.load(std::memory_order_relaxed);

    printf("Transmission:\n");
    printf("  TX Packets:          %lu\n", total_pkts);
    printf("  TX Points:           %lu\n", total_pts);
    printf("  TX Bytes:            %lu (%.2f MB)\n", total_bytes, total_bytes / 1048576.0);
    printf("  Avg pts/packet:      %.1f\n", total_pkts > 0 ? (double)total_pts / total_pkts : 0.0);
    printf("  Avg pts/callback:    %.1f\n", total_cbs > 0 ? (double)total_pts / total_cbs : 0.0);

    printf("\nSegmentation:\n");
    printf("  Segmented packets:   %lu\n", stats_segmented_packets.load(std::memory_order_relaxed));
    printf("  Segmented points:    %lu\n", stats_points_segmented.load(std::memory_order_relaxed));
    printf("  Dropped (cap):       %lu ⚠\n", stats_points_dropped_cap.load(std::memory_order_relaxed));

    printf("\nErrors:\n");
    printf("  Dropped packets:     %lu\n", stats_dropped_packets.load(std::memory_order_relaxed));
    printf("  EAGAIN count:        %lu\n", stats_send_eagain.load(std::memory_order_relaxed));
    printf("  Filtered points:     %lu\n", stats_filtered_points.load(std::memory_order_relaxed));
    printf("  Seq wraps:           %u\n", stats_seq_wraps.load(std::memory_order_relaxed));

    printf("\nTimestamp:\n");
    printf("  Using fallback:      %s\n", ts_using_fallback ? "YES ⚠" : "no");

    double ts_mean, ts_stddev;
    calc_ts_stats(&ts_mean, &ts_stddev);
    printf("  Δt mean:             %.3f ms\n", ts_mean);
    printf("  Δt stddev:           %.3f ms\n", ts_stddev);

    printf("\nConfiguration:\n");
    printf("  CRC32 enabled:       %d\n", g_crc_enabled ? 1 : 0);
    printf("  Range:               %.1f - %.1f m\n", g_min_range, g_max_range);
    printf("  Downsample:          1/%d\n", g_downsample);

    printf("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n");

    // Acceptance criteria check
    printf("\nAcceptance Criteria:\n");
    bool pass = true;

    // 1. Segmentation zero-loss
    uint64_t dropped_cap = stats_points_dropped_cap.load(std::memory_order_relaxed);
    if (dropped_cap == 0) {
        printf("  ✅ Segmentation: 0 points dropped\n");
    } else {
        printf("  ❌ Segmentation: %lu points dropped (should be 0)\n", dropped_cap);
        pass = false;
    }

    // 2. Device timestamp adoption
    if (!ts_using_fallback) {
        printf("  ✅ Timestamp: Device time adopted\n");
    } else {
        printf("  ⚠️  Timestamp: Using fallback (device time unavailable)\n");
    }

    // 3. Clean shutdown
    uint64_t final_dropped = stats_dropped_packets.load(std::memory_order_relaxed);
    uint64_t final_eagain = stats_send_eagain.load(std::memory_order_relaxed);
    if (final_dropped == 0 && final_eagain == 0) {
        printf("  ✅ Shutdown: No dropped packets\n");
    } else {
        printf("  ⚠️  Shutdown: %lu dropped, %lu EAGAIN\n", final_dropped, final_eagain);
    }

    // 4. CRC status
    if (g_crc_enabled) {
        printf("  ✅ CRC32: Enabled\n");
    } else {
        printf("  ℹ️  CRC32: Disabled\n");
    }

    if (pass && !ts_using_fallback) {
        printf("\n✅ All acceptance criteria passed\n");
    } else if (pass) {
        printf("\n⚠️  Passed with warnings (timestamp fallback)\n");
    } else {
        printf("\n❌ Some criteria failed\n");
    }

    printf("\n✓ Shutdown complete\n");

    return 0;
}
