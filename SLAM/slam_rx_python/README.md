# G1 Live SLAM (Python 구현)

**순수 Python 구현 - 참고용 아카이브**

---

## ⚠️ 참고

이 디렉토리는 **Python 구현 백업**입니다.
실제 사용은 **C++ 최적화 버전**을 권장합니다:
👉 `/home/unitree/AIM-Robotics/SLAM/slam_rx/`

**성능 차이:**
- Python: ~55 ms/frame
- C++ 최적화: ~40 ms/frame (27% 빠름, CPU 15% 절감)

---

## 파일 구조

```
slam_rx_python/
├── live_slam.py           # 메인 엔트리포인트
├── lidar_protocol.py      # 패킷 파서 (Python)
├── frame_builder.py       # 프레임 빌더 (Python)
├── slam_pipeline.py       # KISS-ICP 래퍼
└── README.md              # 이 파일
```

---

## 빠른 실행

### 1. LiDAR 송신기 시작

```bash
cd /home/unitree/AIM-Robotics/SLAM/lidar_tx
./build/lidar_stream config.json 127.0.0.1 9999
```

### 2. SLAM 수신기 시작 (Python 버전)

```bash
cd /home/unitree/AIM-Robotics/SLAM/slam_rx_python
python3 live_slam.py --frame-rate 10 --listen-port 9999
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

## 왜 보관하는가?

1. **레퍼런스 구현**: C++ 구현과 비교/검증용
2. **디버깅**: Python이 더 쉬운 경우
3. **교육/학습**: 알고리즘 이해를 위한 간단한 코드

---

**실제 사용은 C++ 버전 권장**
👉 `/home/unitree/AIM-Robotics/SLAM/slam_rx/README.md`

---

AIM Robotics Team - 2025-11-03
