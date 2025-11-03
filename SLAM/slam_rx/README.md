# G1 Live SLAM

**모듈식 LiDAR SLAM 수신기 - C++ 최적화 버전**

---

## 개요

LiDAR Stream 프로토콜을 수신하여 KISS-ICP 기반 SLAM을 수행하는 시스템입니다.

**주요 특징:**
- ✅ **C++ 최적화 백엔드** (Protocol + Frame Builder)
- ✅ 구조화된 패킷 헤더 파싱 (magic, timestamp, sequence, CRC)
- ✅ 시간 기반 프레임 재구성 (device timestamp 사용)
- ✅ 패킷 손실 검출 (sequence tracking)
- ✅ CRC32 무결성 검증
- ✅ 모듈식 아키텍처 (protocol → frame → SLAM)
- ✅ 정지 안정성 분석 (drift tracking)

---

## 파일 구조

```
/home/unitree/AIM-Robotics/SLAM/slam_rx/
├── live_slam.py           # 메인 엔트리포인트
├── slam_pipeline.py       # KISS-ICP 래퍼
├── build.sh               # C++ 빌드 스크립트
├── cpp/                   # C++ 최적화 구현
│   ├── CMakeLists.txt
│   ├── include/
│   │   ├── lidar_protocol_cpp.hpp
│   │   └── frame_builder_cpp.hpp
│   ├── src/
│   │   ├── lidar_protocol_cpp.cpp       # Protocol Parser (Phase 1)
│   │   ├── lidar_protocol_pybind.cpp
│   │   ├── frame_builder_cpp.cpp        # Frame Builder (Phase 2)
│   │   └── frame_builder_pybind.cpp
│   └── build/             # 빌드 출력 (생성됨)
├── tests/
│   └── test_protocol.py   # 단위 테스트
├── lidar_protocol_cpp.so  # 빌드된 C++ 모듈
├── frame_builder_cpp.so   # 빌드된 C++ 모듈
└── README.md              # 이 파일
```

---

## 빠른 시작

### 1. 의존성 확인

```bash
# 필수 패키지
pip3 install numpy open3d kiss-icp

# C++ 빌드 도구 (이미 설치되어 있어야 함)
# - g++ 또는 clang++
# - cmake
# - python3-dev
# - pybind11
```

### 2. C++ 모듈 빌드

```bash
cd /home/unitree/AIM-Robotics/SLAM/slam_rx

# 첫 빌드 또는 전체 재빌드
./build.sh clean

# 빠른 재빌드 (변경된 파일만)
./build.sh
```

**빌드 성공 시:**
```
========================================
✅ Build successful!
========================================

-rw-rw-r-- 1 unitree unitree 234K Nov  3 10:15 frame_builder_cpp.so
-rw-rw-r-- 1 unitree unitree 198K Nov  3 10:15 lidar_protocol_cpp.so

Testing modules...
✅ Both modules work!
```

### 3. LiDAR 송신기 시작

```bash
cd /home/unitree/AIM-Robotics/SLAM/lidar_tx
./build/lidar_stream config.json 127.0.0.1 9999
```

### 4. SLAM 수신기 시작

```bash
cd /home/unitree/AIM-Robotics/SLAM/slam_rx
python3 live_slam.py --frame-rate 10 --max-range 15.0 --listen-port 9999
```

---

## 사용 예제

### 기본 실행 (실내, 10Hz)

```bash
python3 live_slam.py --frame-rate 10 --max-range 15.0 --listen-port 9999
```

**기대 출력:**
```
======================================================================
G1 Live SLAM
======================================================================
Frame rate:       10 Hz
Range:            0.1 - 15.0 m
Voxel size:       0.15 m
Self-filter:      r=0.3m, z=±0.24m (symmetric)
Min pts/frame:    800
Preset:           indoor (ICP tuning applied)
Debug:            False
======================================================================

✓ UDP socket listening on 0.0.0.0:9999
Listening for LiDAR packets... (Ctrl+C to stop)

======================================================================
[RX] Packets: 1543 (1542.8 pps), Valid: 1543
     Errors: CRC=0, Magic=0, Len=0
[FRAME] Built: 20, Packets: 1543, Avg pts/frame: 7215
        Late: 0, Gaps: 0, Reorder: 0
[SLAM] Processed: 20, Skipped: 0
       Position: [0.12, -0.03, 0.01], Distance: 0.15m
       Map points: 45230
======================================================================
```

### 실외 SLAM (저속, 긴 범위)

```bash
python3 live_slam.py \
    --frame-rate 10 \
    --max-range 50.0 \
    --preset outdoor \
    --listen-port 9999
```

### 디버그 모드 (패킷/프레임 상세 로그)

```bash
python3 live_slam.py --frame-rate 10 --listen-port 9999 --debug
```

**디버그 출력 예시:**
```
[PROTO] ✓ Valid packet: seq=42, ts=1000000000, pts=105, crc=0x12345678
[FRAME] ▶ New frame started: ts=1000000000, seq=42
[FRAME] ■ Frame closed: Frame(pts=7215, pkts=72, dur=0.050s, seq=42-113)
[SLAM] ✓ Frame registered: pts=6892, pos=[0.12, -0.03, 0.01], dist=0.15m
```

### 정지 안정성 테스트 (30초)

```bash
# 로봇 고정 후 실행
python3 live_slam.py --frame-rate 10 --listen-port 9999

# 30초 후 Ctrl+C
```

**종료 시 drift 분석 출력:**
```
======================================================================
POSE DRIFT ANALYSIS (600 samples)
======================================================================
Mean Δt per frame: 0.0085 m
Std deviation:     0.0042 m
Max Δt:            0.0234 m
✅ PASS: Mean drift < 0.02m (stationary stability)
======================================================================
```

---

## 명령줄 옵션

### 네트워크

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--listen-ip` | `0.0.0.0` | UDP 수신 IP |
| `--listen-port` | `9999` | UDP 수신 포트 |

### 프레임 빌딩

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--frame-rate` | `20` | 목표 프레임 레이트 (Hz) |

### 필터링

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--min-range` | `0.1` | 최소 거리 (m) |
| `--max-range` | `20.0` | 최대 거리 (m) |
| `--self-filter-radius` | `0.4` | 로봇 자가 필터 반경 (m) |
| `--self-filter-z-min` | `-0.2` | 로봇 자가 필터 Z 최소 (m) |
| `--self-filter-z-max` | `0.5` | 로봇 자가 필터 Z 최대 (m) |

### SLAM

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--voxel-size` | `0.5` | 복셀 다운샘플링 크기 (m) |
| `--min-points-per-frame` | `800` | 프레임당 최소 포인트 (안정성) |
| `--preset` | `indoor` | 프리셋 (`indoor`, `outdoor`, `custom`) |

### 출력

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--no-save-map` | `False` | 종료 시 맵 저장 안 함 |

### 디버그

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--debug` | `False` | 디버그 로그 활성화 |

---

## 단위 테스트

```bash
cd /home/unitree/AIM-Robotics/SLAM/slam_rx/tests
python3 test_protocol.py
```

**예상 출력:**
```
======================================================================
LiDAR Protocol  Parser - Unit Tests
======================================================================

======================================================================
TEST 1: Valid packet (CRC disabled)
======================================================================
[PROTO] ✓ Valid packet: seq=42, ts=1000000000, pts=2, crc=0x00000000
✓ Test passed: ProtocolStats(total=1, valid=1, ...)

[... 5 more tests ...]

======================================================================
RESULTS: 6/6 passed, 0 failed
======================================================================
```

---

## 성능 (C++ 최적화)

**실측 결과** (Livox Mid-360, 2000 pps, 10 Hz):

| 단계 | Python | C++ | 개선율 |
|------|--------|-----|--------|
| **Phase 1 (Protocol)** | 20.67 ms/frame | 7.68 ms/frame | **2.69x** |
| **Phase 2 (Frame)** | 5.16 ms/frame | 3.25 ms/frame | **1.59x** |
| **SLAM (KISS-ICP)** | 29.13 ms/frame | 29.13 ms/frame | 동일 (이미 C++) |
| **전체** | **54.96 ms** | **40.06 ms** | **1.37x** |

**핵심 효과:**
- ✅ CPU 사용률 **~15% 감소** (로봇 다른 작업에 여유)
- ✅ 전체 처리 시간 **27% 단축** (14.9ms 절감)
- ✅ 배터리 수명 증가
- ✅ 실시간 처리 여유 확보 (10Hz @ 40ms/frame = 40% CPU utilization)

---

## 성능 파라미터

### 프레임 레이트 조정

**증상:** 정지 시 흔들림이 심함
**해결:** 프레임 레이트를 낮춤

```bash
# 10Hz → 5Hz
python3 live_slam.py --frame-rate 5 --listen-port 9999
```

### 저포인트 프레임 스킵

**증상:** 노이즈가 많은 환경에서 불안정
**해결:** `--min-points-per-frame` 증가

```bash
python3 live_slam.py --frame-rate 10 --min-points-per-frame 1200 --listen-port 9999
```

---

## Acceptance Criteria (수용 기준)

### 1. 정지 안정성 ✅
- **조건:** 로봇 고정 30초 동안 mean(|Δt|) < 0.02m
- **확인:** 종료 시 "POSE DRIFT ANALYSIS" 출력 확인

### 2. 프레임 레이트 ✅
- **조건:** frame_rate ≈ CLI 설정값 (±10%)
- **확인:** `[FRAME] Built:` 로그에서 1초당 프레임 수 확인

### 3. CRC/파서 ✅
- **조건:** `crc_fail == 0`, `bad_magic == 0`, `len_mismatch == 0`
- **확인:** `[RX] Errors:` 로그에서 모든 오류 == 0

### 4. 세그먼트 무손실 ✅
- **조건:** `late_packets == 0` (정상 네트워크), `seq_gap` 존재 시에도 정상 동작
- **확인:** `[FRAME] Late:` 및 `Gaps:` 로그 확인

### 5. 종료 ✅
- **조건:** Ctrl+C 시 예외 없이 맵 저장 완료
- **확인:** `slam_map__YYYYMMDD_HHMMSS.pcd` 파일 생성

---

## 트러블슈팅

### 문제: "ModuleNotFoundError: No module named 'lidar_protocol_cpp'"

**원인:** C++ 모듈이 빌드되지 않았거나 .so 파일이 없음

**해결:**
```bash
cd /home/unitree/AIM-Robotics/SLAM/slam_rx

# 전체 재빌드
./build.sh clean

# .so 파일 확인
ls -lh *.so
```

### 문제: 빌드 실패 "pybind11 not found"

**원인:** pybind11 라이브러리가 설치되지 않음

**해결:**
```bash
# Ubuntu/Debian
sudo apt-get install python3-pybind11

# 또는 pip로 설치
pip3 install pybind11
```

### 문제: "No packets received"

**원인:** 송신기 미실행 또는 포트 불일치

**해결:**
```bash
# 송신기 확인
ps aux | grep lidar_stream

# 송신기 재시작
cd /home/unitree/AIM-Robotics/SLAM/lidar_tx
./build/lidar_stream config.json 127.0.0.1 9999
```

### 문제: "CRC failures"

**원인:** 송신기와 수신기 CRC 설정 불일치

**해결:**
```bash
# 송신기 CRC 비활성화
./build/lidar_stream config.json 127.0.0.1 9999

# 또는 수신기에서 CRC 검증 비활성화 (lidar_protocol.py 수정)
# validate_crc=False
```

### 문제: "Frames skipped (low point count)"

**원인:** 필터링 후 포인트가 너무 적음

**해결:**
```bash
# min_points_per_frame 낮춤
python3 live_slam.py --min-points-per-frame 500 --listen-port 9999

# 또는 범위 확장
python3 live_slam.py --max-range 30.0 --listen-port 9999
```

### 문제: "Sequence gaps"

**원인:** UDP 패킷 손실 (네트워크 혼잡)

**확인:** 송신기 로그에서 `Dropped packets` 확인

**해결:**
- 로컬 네트워크 사용 (127.0.0.1)
- 송신기에서 `--downsample 2` 적용 (대역폭 감소)

---

## ZMQ 실시간 스트리밍

맥/원격 PC에서 실시간 맵 확인:

```bash
# Jetson (송신)
python3 live_slam.py \
    --frame-rate 10 \
    --listen-port 9999 \
    --stream-enable \
    --stream-port 7609

# Mac/PC (수신)
python3 viewer_realtime.py \
    --server-ip 192.168.123.164 \
    --port 7609 \
    --flip-y --flip-z
```

---

## 시스템 특징

| 항목 | 설명 |
|------|------|
| 패킷 형식 | 27B header + points (magic, timestamp, sequence, CRC) |
| 타임스탬프 | 장치 하드웨어 시간 (ns 정밀도) |
| 프레임 재구성 | 시간 윈도우 기반 (10Hz = 0.1s periods) |
| 손실 검출 | Sequence tracking |
| CRC 검증 | IEEE 802.3 CRC32 |
| 백엔드 | C++ (pybind11 bindings) |
| 빌드 시스템 | CMake + build.sh wrapper |
| 구조 | 모듈식 (live_slam.py, slam_pipeline.py, cpp/) |

---

## 라이센스

Part of AIM-Robotics project.

---

## 작성자

AIM Robotics Team - 2025-11-02
