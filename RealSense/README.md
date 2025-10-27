# 📷 Intel RealSense D435i 통합

Unitree G1 (Jetson Orin NX)에서 실시간 RGB-D 카메라 스트리밍

---

## 📋 프로젝트 목표

Jetson의 RealSense D435i에서 RGB + Depth 캡처 → UDP로 Mac에 스트리밍 → 실시간 표시

LiDAR 뷰어와 동일한 패턴: 빠른 프로토타이핑을 위한 간단한 UDP/Pickle 방식

---

## 📂 프로젝트 구조

```
RealSense/
├── check_camera.py              ✅ 카메라 감지 및 확인
├── examples/
│   ├── 01_basic_capture.py      📝 로컬 테스트 (프레임 캡처만)
│   ├── 02_stream_sender.py      📝 Jetson → Mac 송신
│   └── 03_stream_receiver.py    📝 Mac 수신 및 표시
├── utils/
│   └── config.py                📝 공통 설정
└── README.md                    📝 이 파일
```

---

## 🔄 데이터 흐름

```
┌─────────────────────────────────────────────────────────┐
│ Jetson (로봇)                                            │
│                                                         │
│  RealSense D435i                                        │
│     ├─ RGB (640x480 BGR) ──┐                           │
│     └─ Depth (640x480 mm)  │                           │
│                            ▼                            │
│  02_stream_sender.py                                    │
│     ├─ NumPy array                                      │
│     ├─ Pickle 직렬화                                     │
│     └─ UDP socket ────────────────────────────────────┐ │
└─────────────────────────────────────────────────────────┘ │
                                                            │
                                                            │ UDP 8889 (RGB)
                                                            │ UDP 8890 (Depth)
                                                            │
┌─────────────────────────────────────────────────────────┐ │
│ Mac (지상국)                                             │ │
│                                                         │ │
│  03_stream_receiver.py                                  │ │
│     ├─ UDP socket ◄─────────────────────────────────────┘
│     ├─ Pickle 역직렬화
│     ├─ NumPy array
│     └─ OpenCV 표시
│         ├─ RGB 창
│         └─ Depth (컬러맵) 창
└─────────────────────────────────────────────────────────┘
```

---

## 📝 구현 단계

### Phase 1: 로컬 테스트 (Jetson만)

**01_basic_capture.py**
- RealSense에서 프레임 캡처
- NumPy 배열로 변환
- 파일로 저장하여 확인
- 카메라 접근 확인용

**목적:** 카메라 기능 확인

---

### Phase 2: 네트워크 전송 (Jetson)

**02_stream_sender.py** (vibes 참고)
- RealSense 초기화
- RGB + Depth 캡처
- Pickle로 직렬화
- UDP로 Mac에 전송
- 간단한 방식 (GStreamer 없이)

**장점:**
- LiDAR 뷰어와 동일한 패턴
- 간단한 구현
- 빠른 프로토타이핑

**제약사항:**
- 높은 대역폭 (압축 없음)
- 해상도 제한 (640x480 권장)

---

### Phase 3: 수신 및 표시 (Mac)

**03_stream_receiver.py** (LiDAR 뷰어 유사)
- UDP 패킷 수신
- Pickle 데이터 역직렬화
- OpenCV로 표시
  - RGB 창
  - Depth 컬러맵 창
- 실시간 FPS 표시

---

## ⚙️ 설정

```python
# utils/config.py
class RealSenseConfig:
    # 해상도
    WIDTH = 640
    HEIGHT = 480
    FPS = 30

    # 네트워크
    MAC_IP = "10.40.100.105"  # Mac IP (LiDAR처럼)
    RGB_PORT = 8889
    DEPTH_PORT = 8890

    # Depth 설정
    DEPTH_MIN = 0      # mm
    DEPTH_MAX = 6000   # mm (6m)
```

---

## 🚀 사용 방법

### 사전 준비

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
cd /home/unitree/AIM-Robotics/RealSense
python3 check_camera.py
```

**2. 스트리밍 시작 (Jetson):**
```bash
cd /home/unitree/AIM-Robotics/RealSense/examples
python3 02_stream_sender.py 10.40.100.105
```

**3. 수신 및 표시 (Mac):**
```bash
python3 03_stream_receiver.py
```

---

## 🎨 Depth 시각화

Depth를 컬러맵으로 변환하여 시각화:

```python
import cv2
import numpy as np

depth_colormap = cv2.applyColorMap(
    cv2.convertScaleAbs(depth_image, alpha=0.03),
    cv2.COLORMAP_JET
)
```

**색상 의미:**
- 🔵 파랑: 가까움 (0-1m)
- 🟢 초록: 중간 (1-3m)
- 🔴 빨강: 멀리 (3-6m)

---

## 📊 vibes와 비교

| 항목 | vibes | 우리 방식 |
|------|-------|----------|
| 인코딩 | H.264 (HW) | Raw (Pickle) |
| 프로토콜 | GStreamer/RTP | UDP/Pickle |
| 복잡도 | 높음 | 낮음 |
| 대역폭 | 낮음 (4Mbps) | 높음 (~30Mbps) |
| 지연 | ~30ms | ~50ms |
| 구현 난이도 | 어려움 | 쉬움 |

**전략:** UDP/Pickle로 간단하게 시작 → 필요시 나중에 GStreamer 추가

---

## 📷 카메라 정보

**감지된 디바이스:**
```
이름:           Intel RealSense D435I
시리얼 번호:    335522070701
펌웨어:         5.13.0.55
USB 타입:       3.2 (USB 3.1)
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
# 결과: 8086:0b3a Intel Corp. RealSense 가 보여야 함

# 카메라 접근 확인
python3 check_camera.py
```

### "Device or Resource Busy" 에러

```bash
# USB 케이블 재연결
# 또는 카메라 사용 중인 프로세스 종료
pkill -9 python3
```

### 네트워크 문제

```bash
# Mac IP 확인
ifconfig | grep "inet " | grep -v 127.0.0.1

# UDP 연결 테스트
# Mac에서:
nc -ul 8889

# Jetson에서:
echo "test" | nc -u 10.40.100.105 8889
```

---

## 🎯 개발 체크리스트

- [x] 카메라 감지 스크립트 (check_camera.py)
- [x] USB 3.2 연결 확인
- [x] 프로젝트 구조 계획
- [ ] 01_basic_capture.py 작성
- [ ] 로컬 프레임 캡처 테스트
- [ ] 02_stream_sender.py 작성
- [ ] 03_stream_receiver.py 작성
- [ ] 네트워크 스트리밍 테스트
- [ ] 문서 작성 완료

---

## 📚 참고 자료

**vibes 프로젝트:**
- `/home/unitree/unitree_g1_vibes/stream_realsense.py` - 풀 기능 로컬 뷰어
- `/home/unitree/unitree_g1_vibes/jetson_realsense_stream.py` - 프로덕션 스트리밍
- `/home/unitree/unitree_g1_vibes/receive_realsense_gst.py` - GStreamer 수신기

**librealsense 예제:**
- `/home/unitree/unitree_g1_vibes/librealsense/wrappers/python/examples/`

---

Made with 💡 by AIM Robotics
