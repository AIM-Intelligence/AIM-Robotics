#!/usr/bin/env python3
"""
G1 LiDAR 실시간 3D 뷰어
"""
import socket
import struct
import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import matplotlib.animation as animation
import select

# UDP 설정
UDP_IP = "0.0.0.0"
UDP_PORT = 8888

# 소켓 생성 (non-blocking)
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((UDP_IP, UDP_PORT))
sock.setblocking(False)  # Non-blocking mode

FLIP_X = False  # X축 반전 여부
FLIP_Y = True   # Y축 반전 여부
FLIP_Z = True   # Z축 반전 여부

# 포인트 클라우드 버퍼
# 로봇이 멈춰있으면 계속 쌓아서 더 완전한 뷰 제공
points_buffer = []  # 모든 최근 포인트 저장
max_points = 30000  # 최대 30,000 포인트 유지 (약 1.5초 분량)
clear_interval = 200 # 200 프레임마다만 초기화 (약 10초 - 거의 안 지움)

# 필터링 설정
MAX_RANGE = 10.0    # 최대 거리 (m) - 이것보다 먼 포인트는 노이즈로 간주
MIN_RANGE = 0.1     # 최소 거리 (m) - 센서 너무 가까운 포인트 제거

# Figure 설정
fig = plt.figure(figsize=(12, 9))
ax = fig.add_subplot(111, projection='3d')

# 초기 설정
ax.set_xlabel('X (m)')
ax.set_ylabel('Y (m)')
ax.set_zlabel('Z (m)')
ax.set_title('G1 LiDAR - Real-time Point Cloud')

# 축 범위 설정
ax.set_xlim([-3, 3])
ax.set_ylim([-3, 3])
ax.set_zlim([0, 3])  # 바닥을 0으로

scatter = ax.scatter([], [], [], c='b', marker='.', s=1)

# LiDAR 위치 마커 (원점에 빨간 점)
lidar_marker = ax.scatter([0], [0], [0], c='red', marker='o', s=50, label='LiDAR')
ax.legend(loc='upper right')

frame_count = 0
packet_count = 0
total_points_received = 0
estimated_height = None  # 추정된 LiDAR 높이
ground_z_offset = 0.0    # 바닥을 z=0으로 만들기 위한 오프셋

def update_plot(frame):
    global points_buffer, frame_count, packet_count, total_points_received, estimated_height, ground_z_offset

    # UDP로 데이터 수신 (non-blocking)
    packets_this_frame = 0
    points_this_frame = 0

    while True:
        try:
            data, addr = sock.recvfrom(65536)
            packets_this_frame += 1
            packet_count += 1

            # 포인트 파싱 (각 포인트: 3 floats + 1 byte = 13 bytes)
            num_points = len(data) // 13
            points_this_frame += num_points
            total_points_received += num_points

            for i in range(num_points):
                offset = i * 13
                x, y, z = struct.unpack('fff', data[offset:offset+12])
                intensity = struct.unpack('B', data[offset+12:offset+13])[0]

                # LiDAR 거꾸로 장착 보정 (X축 기준 180도 회전)
                if FLIP_X:
                    x = -x
                if FLIP_Y:
                    y = -y
                if FLIP_Z:
                    z = -z

                # 거리 필터링 (노이즈 제거)
                distance = np.sqrt(x*x + y*y + z*z)
                if MIN_RANGE < distance < MAX_RANGE:
                    points_buffer.append([x, y, z, intensity])

        except BlockingIOError:
            # 더 이상 읽을 데이터가 없음
            break
        except Exception as e:
            print(f"Error: {e}")
            break

    # 주기적으로 버퍼 완전히 비우기 (깨끗한 현재 뷰)
    if frame_count % clear_interval == 0 and frame_count > 0:
        print(f"[Frame {frame_count}] Buffer cleared - new scan started")
        points_buffer.clear()

    # 디버그 출력
    if packets_this_frame > 0:
        print(f"Update #{frame_count}: {packets_this_frame} packets, {points_this_frame} points, "
              f"buffer: {len(points_buffer)} points")

    # 너무 많은 포인트가 쌓이면 오래된 것 제거
    if len(points_buffer) > max_points:
        points_buffer = points_buffer[-max_points:]

    # 포인트가 있으면 시각화
    if len(points_buffer) > 0:
        points = np.array(points_buffer)

        # 바닥 높이 자동 추정 및 보정 (충분한 데이터가 있을 때)
        if len(points) > 100 and frame_count % 30 == 0:  # 30프레임마다 업데이트
            # Z 좌표 하위 10%를 바닥으로 간주
            z_coords = points[:, 2]
            ground_threshold = np.percentile(z_coords, 10)
            ground_points = points[z_coords <= ground_threshold]

            if len(ground_points) > 10:
                # 바닥의 평균 Z 좌표
                ground_z = np.mean(ground_points[:, 2])
                # 바닥을 z=0으로 만들기 위한 오프셋
                ground_z_offset = -ground_z
                # LiDAR 높이 = 오프셋 (바닥에서 LiDAR까지)
                estimated_height = ground_z_offset

        # 모든 포인트에 오프셋 적용 (바닥을 z=0으로)
        if ground_z_offset != 0:
            points[:, 2] += ground_z_offset

            # LiDAR 마커 위치 업데이트
            lidar_marker._offsets3d = ([0], [0], [estimated_height])

        # 다운샘플링 (vibes 코드 방식 - 성능 향상)
        if len(points) > 100000:
            step = len(points) // 100000
            points = points[::step]

        # 색상은 거리 기반
        distances = np.sqrt(points[:, 0]**2 + points[:, 1]**2 + points[:, 2]**2)
        colors = distances  # 거리 값 그대로 사용 (matplotlib이 자동 정규화)

        # Scatter plot 업데이트
        scatter._offsets3d = (points[:, 0], points[:, 1], points[:, 2])
        scatter.set_array(colors)
        scatter.set_cmap('jet')  # jet: 파란색(가까움) -> 빨간색(멀음)

        if frame_count % 10 == 0:
            filtered_count = len(points_buffer)
            displayed_count = len(points)
            height_text = f" | Height: {estimated_height:.2f}m" if estimated_height else ""
            title = f'G1 LiDAR - {displayed_count} points{height_text}'
            ax.set_title(title)

    frame_count += 1
    return scatter,

print("G1 LiDAR Real-time Viewer")
print(f"Listening on UDP: {UDP_IP}:{UDP_PORT}")
print("Start streaming program:")
print("  ./build/g1_lidar_stream g1_mid360_config.json <Mac_IP> 8888")
print("\nClose window to exit\n")

# 애니메이션 시작 (50ms 간격 = 20 FPS)
ani = animation.FuncAnimation(fig, update_plot, interval=50, blit=False)

plt.show()
