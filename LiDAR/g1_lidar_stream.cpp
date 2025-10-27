#include "livox_lidar_def.h"
#include "livox_lidar_api.h"
#include <stdio.h>
#include <unistd.h>
#include <arpa/inet.h>
#include <sys/socket.h>
#include <string.h>
#include <iostream>

// UDP 설정
int udp_socket;
struct sockaddr_in viewer_addr;

// 간단한 포인트 구조체 (패딩 제거 - 정확히 13 bytes)
struct __attribute__((packed)) SimplePoint {
    float x, y, z;      // 12 bytes
    uint8_t intensity;  // 1 byte
};  // 총 13 bytes (패딩 없음)

void PointCloudCallback(uint32_t handle, const uint8_t dev_type,
                        LivoxLidarEthernetPacket* data, void* client_data) {
    static int count = 0;
    if (data == nullptr) return;

    // Cartesian 좌표계 데이터만 처리
    if (data->data_type == kLivoxLidarCartesianCoordinateHighData) {
        LivoxLidarCartesianHighRawPoint *points =
            (LivoxLidarCartesianHighRawPoint *)data->data;

        // UDP로 전송할 버퍼
        SimplePoint buffer[96];
        int valid_count = 0;

        for (int i = 0; i < data->dot_num && i < 96; i++) {
            // (0,0,0) 포인트는 무효 데이터이므로 제외
            if (points[i].x != 0 || points[i].y != 0 || points[i].z != 0) {
                buffer[valid_count].x = points[i].x / 1000.0f;  // mm to m
                buffer[valid_count].y = points[i].y / 1000.0f;
                buffer[valid_count].z = points[i].z / 1000.0f;
                buffer[valid_count].intensity = points[i].reflectivity;
                valid_count++;
            }
        }

        // 유효한 포인트가 있으면 전송
        if (valid_count > 0) {
            int sent = sendto(udp_socket, buffer, valid_count * sizeof(SimplePoint), 0,
                   (struct sockaddr*)&viewer_addr, sizeof(viewer_addr));
            if (++count % 100 == 0) {
                printf("전송 #%d: %d 포인트, %d 바이트 (전체 %d 포인트)\n",
                       count, valid_count, sent, data->dot_num);
            }
        }
    }
}

void WorkModeCallback(livox_status status, uint32_t handle,
                      LivoxLidarAsyncControlResponse *response, void *client_data) {
    if (response == nullptr) return;
    printf("작동 모드 설정: status=%u, ret_code=%u\n", status, response->ret_code);
}

void LidarInfoChangeCallback(const uint32_t handle, const LivoxLidarInfo* info, void* client_data) {
    if (info == nullptr) return;
    printf("LiDAR 연결: S/N %s, IP %s\n", info->sn,
           inet_ntoa(*(struct in_addr*)&info->lidar_ip));

    // Normal 작동 모드로 설정 (포인트 클라우드 스트리밍 시작)
    SetLivoxLidarWorkMode(handle, kLivoxLidarNormal, WorkModeCallback, nullptr);
    printf("포인트 클라우드 스트리밍 시작 요청...\n");
}

int main(int argc, char** argv) {
    const char* config_file = (argc > 1) ? argv[1] : "g1_mid360_config.json";
    const char* viewer_ip = (argc > 2) ? argv[2] : "127.0.0.1";
    int viewer_port = (argc > 3) ? atoi(argv[3]) : 8888;

    printf("G1 LiDAR 스트리밍\n");
    printf("설정: %s\n", config_file);
    printf("뷰어: %s:%d\n", viewer_ip, viewer_port);
    printf("SimplePoint 구조체 크기: %zu bytes (기대값: 13)\n\n", sizeof(SimplePoint));

    // UDP 소켓 생성
    udp_socket = socket(AF_INET, SOCK_DGRAM, 0);
    if (udp_socket < 0) {
        printf("소켓 생성 실패\n");
        return -1;
    }

    memset(&viewer_addr, 0, sizeof(viewer_addr));
    viewer_addr.sin_family = AF_INET;
    viewer_addr.sin_port = htons(viewer_port);
    inet_pton(AF_INET, viewer_ip, &viewer_addr.sin_addr);

    // SDK 초기화
    if (!LivoxLidarSdkInit(config_file)) {
        printf("SDK 초기화 실패\n");
        return -1;
    }

    SetLivoxLidarInfoChangeCallback(LidarInfoChangeCallback, nullptr);
    SetLivoxLidarPointCloudCallBack(PointCloudCallback, nullptr);

    printf("스트리밍 시작...\n");
    printf("종료하려면 Ctrl+C를 누르세요\n\n");

    // 무한 실행
    while (true) {
        sleep(1);
    }

    close(udp_socket);
    LivoxLidarSdkUninit();
    return 0;
}
