#include "livox_lidar_def.h"
#include "livox_lidar_api.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <arpa/inet.h>
#include <sys/socket.h>
#include <signal.h>

// UDP socket configuration
int udp_socket;
struct sockaddr_in viewer_addr;

// Graceful shutdown flag
volatile sig_atomic_t keep_running = 1;

void signal_handler(int signum) {
    (void)signum;
    printf("\n\n🛑 Shutting down gracefully...\n");
    keep_running = 0;
}

// Compact point structure (packed, no padding - exactly 13 bytes)
struct __attribute__((packed)) SimplePoint {
    float x, y, z;      // 12 bytes (3D position in meters)
    uint8_t intensity;  // 1 byte (reflectivity 0-255)
};  // Total: 13 bytes (no padding)

void PointCloudCallback(uint32_t handle, const uint8_t dev_type,
                        LivoxLidarEthernetPacket* data, void* client_data) {
    // Suppress unused parameter warnings
    (void)handle;
    (void)dev_type;
    (void)client_data;

    static int count = 0;

    if (data == nullptr) return;

    // Process only Cartesian coordinate data
    if (data->data_type == kLivoxLidarCartesianCoordinateHighData) {
        LivoxLidarCartesianHighRawPoint *points =
            (LivoxLidarCartesianHighRawPoint *)data->data;

        // Buffer for UDP transmission
        SimplePoint buffer[96];
        int valid_count = 0;

        for (int i = 0; i < data->dot_num && i < 96; i++) {
            // Skip invalid (0,0,0) points
            if (points[i].x != 0 || points[i].y != 0 || points[i].z != 0) {
                buffer[valid_count].x = points[i].x / 1000.0f;  // mm to m
                buffer[valid_count].y = points[i].y / 1000.0f;
                buffer[valid_count].z = points[i].z / 1000.0f;
                buffer[valid_count].intensity = points[i].reflectivity;
                valid_count++;
            }
        }

        // Send if there are valid points
        if (valid_count > 0) {
            ssize_t sent = sendto(udp_socket, buffer, valid_count * sizeof(SimplePoint), 0,
                                  (struct sockaddr*)&viewer_addr, sizeof(viewer_addr));

            if (sent < 0) {
                perror("sendto failed");
            }

            // Print status every 500 packets
            if (++count % 500 == 0) {
                printf("✓ Packet #%d: Streaming %d points\n", count, valid_count);
            }
        }
    }
}

void WorkModeCallback(livox_status status, uint32_t handle,
                      LivoxLidarAsyncControlResponse *response, void *client_data) {
    (void)handle;
    (void)client_data;

    if (response == nullptr) return;
    if (status == 0 && response->ret_code == 0) {
        printf("✓ LiDAR work mode set to NORMAL (streaming active)\n\n");
    } else {
        printf("⚠ WARNING: Work mode status=%u, ret_code=%u\n", status, response->ret_code);
    }
}

void LidarInfoChangeCallback(const uint32_t handle, const LivoxLidarInfo* info, void* client_data) {
    (void)client_data;

    if (info == nullptr) return;

    printf("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n");
    printf("📡 LiDAR Connected\n");
    printf("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n");
    printf("Serial Number: %s\n", info->sn);
    printf("IP Address:    %s\n", inet_ntoa(*(struct in_addr*)&info->lidar_ip));
    printf("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n");

    // Set to Normal mode to start point cloud streaming
    SetLivoxLidarWorkMode(handle, kLivoxLidarNormal, WorkModeCallback, nullptr);
    printf("Requesting point cloud streaming...\n");
}

int main(int argc, char** argv) {
    const char* config_file = (argc > 1) ? argv[1] : "g1_mid360_config.json";
    const char* viewer_ip = (argc > 2) ? argv[2] : "127.0.0.1";
    int viewer_port = (argc > 3) ? atoi(argv[3]) : 8888;

    printf("========================================\n");
    printf("G1 LiDAR Streaming Server\n");
    printf("========================================\n");
    printf("Config:       %s\n", config_file);
    printf("Viewer:       %s:%d\n", viewer_ip, viewer_port);
    printf("Data format:  SimplePoint (%zu bytes)\n", sizeof(SimplePoint));
    printf("----------------------------------------\n\n");

    // Register signal handler for graceful shutdown
    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);

    // Create UDP socket
    udp_socket = socket(AF_INET, SOCK_DGRAM, 0);
    if (udp_socket < 0) {
        printf("❌ ERROR: Failed to create UDP socket\n");
        return -1;
    }

    // Set socket timeout (5 seconds)
    struct timeval timeout;
    timeout.tv_sec = 5;
    timeout.tv_usec = 0;
    if (setsockopt(udp_socket, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout)) < 0) {
        printf("⚠ WARNING: Failed to set socket timeout\n");
    }

    memset(&viewer_addr, 0, sizeof(viewer_addr));
    viewer_addr.sin_family = AF_INET;
    viewer_addr.sin_port = htons(viewer_port);
    inet_pton(AF_INET, viewer_ip, &viewer_addr.sin_addr);
    printf("✓ UDP socket created (target: %s:%d)\n", viewer_ip, viewer_port);

    // Initialize Livox SDK
    if (!LivoxLidarSdkInit(config_file)) {
        printf("❌ ERROR: Livox SDK initialization failed\n");
        return -1;
    }
    printf("✓ Livox SDK initialized\n");

    SetLivoxLidarInfoChangeCallback(LidarInfoChangeCallback, nullptr);
    SetLivoxLidarPointCloudCallBack(PointCloudCallback, nullptr);

    printf("\n🚀 Streaming started...\n");
    printf("Press Ctrl+C to stop\n\n");

    // Main loop - keep running until interrupted
    while (keep_running) {
        sleep(1);
    }

    // Cleanup
    printf("Cleaning up resources...\n");
    close(udp_socket);
    LivoxLidarSdkUninit();
    printf("✓ Shutdown complete\n");
    return 0;
}
