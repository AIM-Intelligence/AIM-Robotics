#!/usr/bin/env python3
"""
G1 LiDAR 실시간 3D 뷰어 - 단순 버전
- 필터링 최소화 (모든 점 표시)
- 카메라 제한 없음 (자유롭게 축소 가능)
- 빠른 렌더링
"""
import socket
import struct
import numpy as np
import open3d as o3d
import threading
import time
from matplotlib import cm

# UDP 설정
UDP_IP = "0.0.0.0"
UDP_PORT = 8888

# 좌표 변환
FLIP_X = False
FLIP_Y = True
FLIP_Z = True

# 간단한 필터링만
MAX_RANGE = 15.0    # 최대 거리만 제한
MIN_RANGE = 0.1    # 아주 가까운 것만 제거

# 전역 변수
points_xyz = []
points_lock = threading.Lock()
running = True

def udp_receiver():
    """UDP 수신 스레드 - 필터링 최소화"""
    global points_xyz, running

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((UDP_IP, UDP_PORT))
    sock.setblocking(False)

    print(f"UDP listening on {UDP_IP}:{UDP_PORT}")

    local_buffer = []

    # 성능 측정 변수
    packet_count = 0
    recv_times = []
    parse_times = []
    lock_times = []
    last_recv_time = None

    while running:
        try:
            recv_start = time.perf_counter()
            data, addr = sock.recvfrom(65536)
            recv_end = time.perf_counter()
            recv_time = (recv_end - recv_start) * 1000  # ms

            # 패킷 간 간격 측정
            if last_recv_time is not None:
                packet_interval = (recv_start - last_recv_time) * 1000  # ms
            else:
                packet_interval = 0
            last_recv_time = recv_start

            parse_start = time.perf_counter()
            num_points = len(data) // 13

            for i in range(num_points):
                offset = i * 13
                x, y, z = struct.unpack('fff', data[offset:offset+12])

                # 좌표 변환
                if FLIP_X:
                    x = -x
                if FLIP_Y:
                    y = -y
                if FLIP_Z:
                    z = -z

                # 아주 간단한 필터링만 (거리만)
                distance = np.sqrt(x*x + y*y + z*z)
                if MIN_RANGE < distance < MAX_RANGE:
                    local_buffer.append([x, y, z])

            parse_end = time.perf_counter()
            parse_time = (parse_end - parse_start) * 1000  # ms

            # 주기적으로 메인 버퍼에 복사
            lock_time = 0
            if len(local_buffer) > 1000:
                lock_start = time.perf_counter()
                with points_lock:
                    points_xyz.extend(local_buffer)
                    # 너무 많으면 오래된 것만 제거
                    if len(points_xyz) > 70000:
                        points_xyz = points_xyz[-50000:]
                lock_end = time.perf_counter()
                lock_time = (lock_end - lock_start) * 1000  # ms
                local_buffer.clear()

            recv_times.append(recv_time)
            parse_times.append(parse_time)
            lock_times.append(lock_time)
            packet_count += 1

            # 100 패킷마다 통계 출력
            if packet_count % 100 == 0:
                avg_recv = sum(recv_times) / len(recv_times)
                avg_parse = sum(parse_times) / len(parse_times)
                avg_lock = sum([t for t in lock_times if t > 0]) / max(1, len([t for t in lock_times if t > 0]))
                print(f"\n[UDP 수신 성능 - {packet_count} 패킷]")
                print(f"  수신: {avg_recv:.3f} ms (avg), {max(recv_times):.3f} ms (max)")
                print(f"  파싱: {avg_parse:.3f} ms (avg), {max(parse_times):.3f} ms (max)")
                if avg_lock > 0:
                    print(f"  Lock: {avg_lock:.3f} ms (avg)")
                print(f"  패킷 간격: {packet_interval:.3f} ms")
                print(f"  버퍼 크기: {len(points_xyz)} 포인트")
                recv_times.clear()
                parse_times.clear()
                lock_times.clear()

        except BlockingIOError:
            time.sleep(0.001)
        except Exception as e:
            if running:
                print(f"Error: {e}")
            break

    sock.close()

def main():
    global points_xyz, running

    # 색상 Lookup Table 생성 (초기화 시 1번만)
    COLORMAP_SIZE = 256
    COLORMAP_LUT = cm.jet(np.linspace(0, 1, COLORMAP_SIZE))[:, :3]

    print("=" * 60)
    print("G1 LiDAR Viewer - Simple & Fast (Color LUT)")
    print("=" * 60)
    print("\n최적화:")
    print(f"  - 색상 Lookup Table (256색) - 4배 빠름")
    print("\n설정:")
    print(f"  거리 범위: {MIN_RANGE}-{MAX_RANGE}m")
    print(f"  필터링: 최소화 (모든 점 표시)")
    print("\n조작:")
    print("  마우스 드래그: 회전")
    print("  마우스 휠: 줌 (제한 없음!)")
    print("  Shift + 마우스 드래그: 카메라 팬(이동)")
    print("\n  카메라 이동 (FPS 스타일):")
    print("    W / ↑ : 앞으로")
    print("    S / ↓ : 뒤로")
    print("    A / ← : 왼쪽")
    print("    D / → : 오른쪽")
    print("    E / Page Up   : 위로")
    print("    C / Page Down : 아래로")
    print("\n  R: 카메라 리셋")
    print("  Q: 종료\n")
    
    # UDP 수신 시작
    receiver = threading.Thread(target=udp_receiver, daemon=True)
    receiver.start()

    # Open3D 시각화 (키보드 콜백 지원)
    vis = o3d.visualization.VisualizerWithKeyCallback()
    vis.create_window(window_name='G1 LiDAR - Simple Viewer',
                      width=1280, height=720)
    
    # 포인트 클라우드 객체
    pcd = o3d.geometry.PointCloud()
    
    # 좌표 프레임
    coord = o3d.geometry.TriangleMesh.create_coordinate_frame(size=0.5)
    
    vis.add_geometry(pcd)
    vis.add_geometry(coord)
    
    # 렌더 옵션 - 점들이 사라지지 않도록 설정
    opt = vis.get_render_option()
    opt.background_color = np.array([0.05, 0.05, 0.05])
    opt.point_size = 2.0  # 포인트 크기 증가

    # 중요: 모든 포인트가 항상 보이도록 설정
    opt.point_show_normal = False  # Normal 표시 끄기
    opt.mesh_show_wireframe = False
    opt.mesh_show_back_face = False

    # 카메라 초기 설정 - 간단한 방법
    ctr = vis.get_view_control()

    # Clipping plane 조정 - 아주 가까운 것부터 아주 먼 것까지 모두 렌더링
    # 이게 핵심! 각도에 따라 점이 사라지는 것을 방지
    ctr.set_constant_z_near(0.1)   # 아주 가까운 것도 보임 (0.001m = 1mm)
    ctr.set_constant_z_far(15.0)   # 아주 먼 것도 보임 (1000m)

    # 기본 위치 설정 (간단!)
    # 카메라가 Y축 음의 방향에서 원점을 바라봄
    ctr.set_front([0, 1, 0])       # 카메라가 +Y 방향을 봄 (앞쪽)
    ctr.set_lookat([0, 0, 0.5])    # 원점보다 약간 위를 봄
    ctr.set_up([0, 0, 1])          # Z축이 위 (하늘 방향)
    ctr.set_zoom(0.3)              # 적당히 멀리서 시작

    # 카메라 이동 함수들
    move_step = 0.5  # 이동 스텝 (미터)

    def move_forward(vis):
        ctr = vis.get_view_control()
        ctr.camera_local_translate(0, 0, -move_step)  # 앞으로
        return False

    def move_backward(vis):
        ctr = vis.get_view_control()
        ctr.camera_local_translate(0, 0, move_step)  # 뒤로
        return False

    def move_left(vis):
        ctr = vis.get_view_control()
        ctr.camera_local_translate(-move_step, 0, 0)  # 왼쪽
        return False

    def move_right(vis):
        ctr = vis.get_view_control()
        ctr.camera_local_translate(move_step, 0, 0)  # 오른쪽
        return False

    def move_up(vis):
        ctr = vis.get_view_control()
        ctr.camera_local_translate(0, -move_step, 0)  # 위로
        return False

    def move_down(vis):
        ctr = vis.get_view_control()
        ctr.camera_local_translate(0, move_step, 0)  # 아래로
        return False

    def reset_camera(vis):
        ctr = vis.get_view_control()
        ctr.set_front([0, 1, 0])
        ctr.set_lookat([0, 0, 0.5])
        ctr.set_up([0, 0, 1])
        ctr.set_zoom(0.3)
        print("Camera reset")
        return False

    def quit_viewer(vis):
        global running
        running = False
        print("Exiting...")
        return False

    # 키보드 콜백 등록
    # 화살표 키
    vis.register_key_callback(265, move_forward)   # ↑ Up arrow
    vis.register_key_callback(264, move_backward)  # ↓ Down arrow
    vis.register_key_callback(263, move_left)      # ← Left arrow
    vis.register_key_callback(262, move_right)     # → Right arrow
    # WASD (FPS 스타일)
    vis.register_key_callback(ord('W'), move_forward)
    vis.register_key_callback(ord('S'), move_backward)
    vis.register_key_callback(ord('A'), move_left)
    vis.register_key_callback(ord('D'), move_right)
    # 상하 이동
    vis.register_key_callback(266, move_up)        # Page Up
    vis.register_key_callback(267, move_down)      # Page Down
    vis.register_key_callback(ord('E'), move_up)    # E = 위로
    vis.register_key_callback(ord('C'), move_down)  # C = 아래로
    # 기타
    vis.register_key_callback(ord('R'), reset_camera)
    vis.register_key_callback(ord('Q'), quit_viewer)
    
    frame = 0
    last_update = time.time()

    # 렌더링 성능 측정 (정확한 측정)
    frame_times = []
    lock_numpy_times = []  # Lock + NumPy (합쳐서 측정)
    color_times = []
    open3d_times = []
    render_times = []

    print("Waiting for data...")

    try:
        while running:
            current_time = time.time()

            # 50ms마다 업데이트 (20 FPS)
            if current_time - last_update > 0.05:
                frame_start = time.perf_counter()

                # === 1. Lock + NumPy 변환 (함께 측정) ===
                lock_numpy_start = time.perf_counter()
                xyz = None
                with points_lock:
                    if len(points_xyz) > 0:
                        xyz = np.array(points_xyz)
                lock_numpy_end = time.perf_counter()
                lock_numpy_time = (lock_numpy_end - lock_numpy_start) * 1000  # ms

                if xyz is not None and len(xyz) > 0:
                    # === 2. 색상 계산 (Lookup Table 최적화) ===
                    color_start = time.perf_counter()
                    distances = np.linalg.norm(xyz, axis=1)
                    d_min, d_max = distances.min(), distances.max()
                    if d_max > d_min:
                        normalized = (distances - d_min) / (d_max - d_min)
                    else:
                        normalized = np.zeros_like(distances)
                    # Lookup Table 사용 (빠름!)
                    indices = (normalized * 255).astype(np.uint8)
                    colors = COLORMAP_LUT[indices]
                    color_end = time.perf_counter()
                    color_time = (color_end - color_start) * 1000  # ms

                    # === 3. Open3D 업데이트 ===
                    open3d_start = time.perf_counter()
                    pcd.points = o3d.utility.Vector3dVector(xyz)
                    pcd.colors = o3d.utility.Vector3dVector(colors)
                    vis.update_geometry(pcd)
                    open3d_end = time.perf_counter()
                    open3d_time = (open3d_end - open3d_start) * 1000  # ms

                    frame_end = time.perf_counter()
                    frame_time = (frame_end - frame_start) * 1000  # ms

                    # 통계 수집
                    frame_times.append(frame_time)
                    lock_numpy_times.append(lock_numpy_time)
                    color_times.append(color_time)
                    open3d_times.append(open3d_time)

                    # === 20 프레임마다 통계 출력 ===
                    if frame % 20 == 0 and len(frame_times) > 0:
                        avg_frame = sum(frame_times) / len(frame_times)
                        avg_lock_numpy = sum(lock_numpy_times) / len(lock_numpy_times)
                        avg_color = sum(color_times) / len(color_times)
                        avg_open3d = sum(open3d_times) / len(open3d_times)

                        # 렌더러 업데이트 평균
                        avg_render = sum(render_times) / len(render_times) if len(render_times) > 0 else 0

                        # 합계 검증
                        measured_sum = avg_lock_numpy + avg_color + avg_open3d
                        other_time = avg_frame - measured_sum

                        print(f"\n[렌더링 성능 - Frame {frame}]")
                        print(f"  포인트 수: {len(xyz):,}")
                        print(f"  1. Lock+NumPy: {avg_lock_numpy:.3f} ms ({avg_lock_numpy/avg_frame*100:.1f}%)")
                        print(f"  2. 색상 계산 (LUT): {avg_color:.3f} ms ({avg_color/avg_frame*100:.1f}%)")
                        print(f"  3. Open3D 업데이트: {avg_open3d:.3f} ms ({avg_open3d/avg_frame*100:.1f}%)")
                        print(f"  4. 기타: {other_time:.3f} ms ({other_time/avg_frame*100:.1f}%)")
                        print(f"  ─────────────────────────────────────")
                        print(f"  프레임 총 시간: {avg_frame:.3f} ms (= {1000/avg_frame:.1f} FPS)")
                        if avg_render > 0:
                            print(f"  렌더러 업데이트: {avg_render:.3f} ms (poll_events + update_renderer)")

                        # 통계 초기화
                        frame_times.clear()
                        lock_numpy_times.clear()
                        color_times.clear()
                        open3d_times.clear()
                        render_times.clear()

                    frame += 1

                last_update = current_time

            # === 4. 렌더러 업데이트 (별도 측정) ===
            render_start = time.perf_counter()
            if not vis.poll_events():
                break
            vis.update_renderer()
            render_end = time.perf_counter()
            render_times.append((render_end - render_start) * 1000)

            time.sleep(0.001)
    
    except KeyboardInterrupt:
        print("\nStopped by user")
    finally:
        running = False
        vis.destroy_window()
        receiver.join(timeout=1.0)
    
    print(f"Total frames: {frame}")

if __name__ == "__main__":
    main()
