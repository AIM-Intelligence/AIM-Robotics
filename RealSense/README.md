# 📷 Intel RealSense D435i

Unitree G1 (Jetson Orin NX)에서 실시간 RGB-D 카메라 스트리밍

<table>
<tr>
<td width="50%">

**RGB 스트림**

![RGB Stream](RGB.png)

</td>
<td width="50%">

**Depth 스트림 (컬러맵)**

![Depth Stream](Depth.png)

</td>
</tr>
</table>

## 📋 프로젝트 목표

Jetson의 RealSense D435i에서 RGB + Depth 캡처 → 압축 → 패킷 분할 → UDP로 Mac에 스트리밍 → 실시간 표시

LiDAR 뷰어와 동일한 패턴: 빠른 프로토타이핑을 위한 간단한 UDP 방식


---

## 📂 프로젝트 구조

```
RealSense/
├── examples/
│   ├── 00_check_camera.py       ✅ 카메라 감지 및 확인
│   ├── 01_basic_capture.py      ✅ 로컬 테스트 (프레임 캡처 + 분석)
│   ├── 02_stream_sender.py      ✅ Jetson → Mac 송신 (압축 + 패킷 분할)
│   └── 03_stream_receiver.py    ✅ Mac 수신 및 표시
└── README.md                    📝 이 파일
```

---

## 🔄 데이터 흐름

```
┌──────────────────────────────────────────────────────────────┐
│ Jetson (로봇)                                                 │
│                                                              │
│  RealSense D435i                                             │
│     ├─ RGB (640x480 BGR)  ──┐                               │
│     └─ Depth (640x480 mm)   │                               │
│                             ▼                                │
│  02_stream_sender.py                                         │
│     ├─ JPEG 압축 (RGB: 900KB → 22KB)                         │
│     ├─ PNG 압축 (Depth: 600KB → 190KB)                       │
│     ├─ 패킷 분할 (60KB 청크)                                  │
│     └─ UDP socket ────────────────────────────────────────┐  │
└──────────────────────────────────────────────────────────────┘  │
                                                                 │
                                                                 │ UDP 8889 (RGB)
                                                                 │ UDP 8890 (Depth)
                                                                 │
┌──────────────────────────────────────────────────────────────┐  │
│ Mac (지상국)                                                  │  │
│                                                              │  │
│  03_stream_receiver.py                                       │  │
│     ├─ UDP socket ◄──────────────────────────────────────────┘
│     ├─ 패킷 재조립
│     ├─ JPEG/PNG 디코딩
│     └─ OpenCV 표시
│         ├─ RGB 창
│         └─ Depth (컬러맵) 창
└──────────────────────────────────────────────────────────────┘
```

---

## 📝 구현 단계

### ✅ Phase 1: 로컬 테스트 (완료)

**00_check_camera.py**
- RealSense 디바이스 감지
- USB 연결 확인
- 기본 프레임 캡처 테스트
- 30프레임 안정화 (Device Busy 방지)

**01_basic_capture.py**
- RGB + Depth 프레임 캡처
- 상세 통계 분석 (depth 분포, 색상 채널 등)
- 샘플 픽셀 값 표시
- 파일 저장 기능 제거 (화면 출력만)

**목적:** 카메라 기능 확인 및 데이터 검증

---

### ✅ Phase 2: 네트워크 스트리밍 (완료)

**02_stream_sender.py** (Jetson)
- RealSense 초기화 및 30프레임 안정화
- **JPEG 압축** (RGB: 85% 품질, ~22KB)
- **PNG 압축** (Depth: 무손실 16-bit, ~190KB)
- **패킷 분할** (60KB 청크, UDP 제한 회피)
- UDP로 Mac에 전송 (별도 포트)
- 실시간 FPS 및 전송량 표시

**03_stream_receiver.py** (Mac)
- UDP 패킷 수신 (멀티스레드)
- **패킷 재조립** (sequence_id + chunk_index)
- JPEG/PNG 디코딩
- OpenCV 실시간 표시
- FPS 및 depth 통계 overlay

**핵심 기술:**
- ✅ 압축으로 대역폭 97% 감소 (900KB → 22KB)
- ✅ 패킷 분할로 UDP 크기 제한 해결
- ✅ 무손실 depth 전송 (PNG 16-bit)

---

## 🚀 사용 방법

### 사전 준비

#### RealSense SDK 설치 (Jetson에서 한 번만)

**librealsense 빌드:**
```bash
# 저장소 클론
git clone https://github.com/IntelRealSense/librealsense.git
cd ~/librealsense

# 빌드 (Python 바인딩 포함)
mkdir build && cd build
cmake .. -DBUILD_PYTHON_BINDINGS:bool=true
make -j$(nproc)
sudo make install
```

**참고:**
- 빌드 시간: 약 10-15분 (Jetson Orin NX 기준)
- Python 바인딩이 필요하므로 `-DBUILD_PYTHON_BINDINGS:bool=true` 필수
- 공식 문서: https://github.com/IntelRealSense/librealsense

#### Python 패키지 설치

**Jetson (로봇):**
```bash
pip3 install pyrealsense2 numpy opencv-python
```

**Mac (지상국):**
```bash
pip3 install numpy opencv-python
```

### 실행

**1. 카메라 연결 확인 (Jetson):**
```bash
cd /home/unitree/AIM-Robotics/RealSense/examples
python3 00_check_camera.py
```

**2. 로컬 캡처 테스트 (Jetson, 선택):**
```bash
python3 01_basic_capture.py
```

**3. 스트리밍 시작 (Jetson):**
```bash
python3 02_stream_sender.py
```

**참고:** `MAC_IP` 변수를 Mac의 **유선 IP**로 설정하세요!
```python
# 02_stream_sender.py
MAC_IP = "10.40.100.105"  # Mac 유선 IP
```

**4. 수신 및 표시 (Mac):**
```bash
# 03_stream_receiver.py를 Mac으로 복사 후
python3 03_stream_receiver.py
```

종료: `q` 키 또는 `Ctrl+C`


## ⚙️ 설정

```python
# 02_stream_sender.py
MAC_IP = "10.40.100.105"  # Mac IP (유선 권장!)
RGB_PORT = 8889           # RGB 스트림 포트
DEPTH_PORT = 8890         # Depth 스트림 포트
CHUNK_SIZE = 60000        # 60KB 청크 (UDP 안전 크기)

# 스트림 설정
Width: 640
Height: 480
FPS: 30

# 압축 설정
JPEG Quality: 85          # RGB 압축률
PNG: Lossless 16-bit      # Depth 무손실
```

---

## 🎨 Depth 시각화

Depth를 JET 컬러맵으로 변환:

```python
# 0-10m 범위를 0-255로 정규화
depth_normalized = np.clip(depth_image / 10000.0 * 255, 0, 255).astype(np.uint8)
depth_colormap = cv2.applyColorMap(depth_normalized, cv2.COLORMAP_JET)
```

**색상 의미:**
- 🔵 파랑/보라: 가까움 (0-2m)
- 🟢 초록/노랑: 중간 (2-5m)
- 🔴 빨강: 멀리 (5-10m)

---

## 📊 vibes와 비교

| 항목 | vibes | 우리 구현 |
|------|-------|----------|
| 인코딩 | H.264 (HW) | JPEG/PNG (SW) |
| 프로토콜 | GStreamer/RTP | UDP + 패킷 분할 |
| 복잡도 | 높음 | 중간 |
| 대역폭 | 낮음 (4Mbps) | 중간 (~6Mbps) |
| 구현 난이도 | 어려움 | 보통 |
| Depth 품질 | - | 무손실 16-bit |

**전략:** 간단한 UDP + 압축으로 시작 → 필요시 나중에 GStreamer 추가

---

## 📷 카메라 정보

**감지된 디바이스:**
```
이름:           Intel RealSense D435I
시리얼 번호:    335522070701
펌웨어:         5.13.0.55
USB 타입:       3.2 (USB 3.1 포트)
```

**사용 가능한 센서:**
- ✅ Stereo Module (Depth 센서)
- ✅ RGB Camera (컬러 이미지)
- ✅ Motion Module (IMU - 자이로/가속도계)

**테스트된 스트림:**
- ✅ Depth: 640x480 @ 30fps (16-bit, 밀리미터)
- ✅ Color: 640x480 @ 30fps (8-bit BGR)

---

## 🔧 문제 해결

### 카메라가 감지되지 않음

```bash
# USB 연결 확인
lsusb | grep -i intel
# 결과: 8086:0b3a Intel Corp. 가 보여야 함

# USB 3.0 포트 확인 (파란색 포트 사용)
# 카메라 접근 확인
python3 00_check_camera.py
```

### "Device or Resource Busy" 에러

**원인:** 카메라 리소스가 완전히 해제되지 않음

**해결:**
1. 스크립트 종료 후 0.5초 대기 (자동 구현됨)
2. 30프레임 안정화 후 캡처 (자동 구현됨)
3. USB 재연결

```bash
# 프로세스 강제 종료 (필요시)
pkill -9 python3
```

### "Network is unreachable" 에러

**원인:** Mac IP가 잘못되었거나 네트워크 연결 끊김

**해결:**

**Mac에서 IP 확인:**
```bash
# 모든 네트워크 IP 확인
ifconfig | grep "inet " | grep -v 127.0.0.1

# 출력 예시:
#   inet 10.0.0.2 netmask ...        <- WiFi (무선)
#   inet 10.40.100.105 netmask ...   <- Ethernet (유선) ✅ 이거 사용!
```

**유선 IP 찾는 방법:**
1. `ifconfig | grep "inet " | grep -v 127.0.0.1` 실행
2. 여러 IP가 나오면:
   - **유선 (Ethernet)**: 보통 `10.40.x.x` 또는 `192.168.x.x` 형식
   - **무선 (WiFi)**: 보통 `10.0.x.x` 형식
3. **System Preferences → Network**에서 Ethernet IP 확인 (GUI 방법)

**특정 인터페이스만 확인:**
```bash
ifconfig en0  # Ethernet (보통)
ifconfig en1  # WiFi (보통)
```

**02_stream_sender.py 수정:**
```python
MAC_IP = "확인한_유선_IP"  # 예: "192.168.1.100"
```

### WiFi 과부하로 연결 끊김

**원인:** RGB + Depth = ~6 MB/s 지속 전송, WiFi는 간섭/레이턴시에 취약

**✅ 해결: 유선 네트워크 사용 (강력 추천)**
- 안정적인 대역폭
- 낮은 레이턴시
- 패킷 손실 최소화

**대체 방법 (유선 불가능한 경우):**
1. **프레임률 낮추기:**
   ```python
   config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 15)  # 30 → 15
   ```

2. **JPEG 품질 낮추기:**
   ```python
   cv2.imencode('.jpg', color_image, [cv2.IMWRITE_JPEG_QUALITY, 70])  # 85 → 70
   ```

3. **해상도 낮추기:**
   ```python
   config.enable_stream(rs.stream.depth, 320, 240, ...)  # 640x480 → 320x240
   ```

### 네트워크 연결 테스트

```bash
# Mac에서 UDP 리스너 실행:
nc -ul 8889

# Jetson에서 테스트 패킷 전송:
echo "test" | nc -u 10.40.100.105 8889
```

---

## 🎯 개발 체크리스트

- [x] 카메라 감지 스크립트 (00_check_camera.py)
- [x] USB 3.2 연결 확인
- [x] 프로젝트 구조 구성
- [x] 01_basic_capture.py 작성 및 테스트
- [x] 로컬 프레임 캡처 및 분석
- [x] JPEG/PNG 압축 구현
- [x] 패킷 분할 전송 구현
- [x] 02_stream_sender.py 작성
- [x] 03_stream_receiver.py 작성
- [x] 네트워크 스트리밍 테스트 (유선)
- [x] 문서 작성 완료

---

## 📚 참고 자료

**vibes 프로젝트:**
- `/home/unitree/unitree_g1_vibes/stream_realsense.py` - 풀 기능 로컬 뷰어
- `/home/unitree/unitree_g1_vibes/jetson_realsense_stream.py` - GStreamer 스트리밍
- `/home/unitree/unitree_g1_vibes/receive_realsense_gst.py` - GStreamer 수신기

**librealsense 예제:**
- `/home/unitree/unitree_g1_vibes/librealsense/wrappers/python/examples/`

**프로젝트 패턴:**
- LiDAR viewer: `/home/unitree/AIM/LiDAR/`

---

## 💡 다음 단계 (선택)

- [ ] H.264 하드웨어 인코딩 (대역폭 추가 감소)
- [ ] GStreamer 통합 (낮은 지연시간)
- [ ] IMU 데이터 통합
- [ ] Point cloud 생성 및 시각화
- [ ] 여러 카메라 동시 지원

---

Made with 💡 by AIM Robotics
