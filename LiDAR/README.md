# 🛰️ G1 LiDAR 스트리밍 & 뷰어

Livox Mid-360 LiDAR를 Jetson Orin NX를 통해 스트리밍하고,
Mac에서 실시간 3D 포인트 클라우드로 시각화하는 예제입니다.

---

## 📋 요구사항 (Prerequisites)

### Jetson Orin NX
- **OS**: Ubuntu 20.04 (JetPack 5.x)
- **Livox SDK2**: `/usr/local/lib/liblivox_lidar_sdk_shared.so` 설치 필요
- **네트워크**:
  - LiDAR 연결: 192.168.123.164 (유선)
  - WiFi: 10.40.100.143 (동일 네트워크)
- **컴파일러**: g++ (C++14 지원)
- **CMake**: 3.10 이상

#### Vendor SDK 설치 (Jetson에서 한 번만 실행)

**Livox SDK2 설치:**
```bash
git clone https://github.com/Livox-SDK/Livox-SDK2.git
cd Livox-SDK2
mkdir build && cd build
cmake .. && make -j$(nproc)
sudo make install
```

### Mac (뷰어 실행)
- **Python**: 3.7 이상
- **라이브러리**:
  ```bash
  pip3 install matplotlib numpy
  ```
- **네트워크**: Jetson과 동일 WiFi (10.40.100.x 대역)

---

## 📂 프로젝트 구조

```
LiDAR/
├── build/                      # 빌드 결과물 (자동 생성)
│   ├── g1_lidar_stream         # 실행 파일 (C++ 컴파일 결과)
│   ├── CMakeCache.txt          # CMake 캐시
│   └── Makefile                # Make 설정
│
├── g1_lidar_stream.cpp         # 메인 C++ 프로그램
│   └─ LiDAR 데이터 수신 → UDP 전송
│
├── g1_mid360_config.json       # LiDAR 네트워크 설정
│   └─ IP, 포트, 멀티캐스트 구성
│
├── lidar_viewer.py             # Mac용 Python 뷰어
│   └─ UDP 수신 → 3D 시각화
│
├── CMakeLists.txt              # CMake 빌드 설정
│   └─ Livox SDK 링크, 컴파일 옵션
│
├── build_lidar.sh              # 빌드 자동화 스크립트
│   └─ mkdir build → cmake → make
│
└── README.md                   # 프로젝트 문서 (이 파일)
```

### 파일별 역할

| 파일 | 타입 | 역할 | 수정 필요 시기 |
|------|------|------|----------------|
| `g1_lidar_stream.cpp` | C++ 소스 | Livox SDK로 LiDAR 데이터 수신, UDP 전송 | 기능 추가/수정 |
| `g1_mid360_config.json` | JSON | LiDAR 네트워크 설정 (IP, 포트) | 네트워크 변경 |
| `lidar_viewer.py` | Python | Mac에서 UDP 수신, matplotlib 3D 시각화 | 시각화 옵션 변경 |
| `CMakeLists.txt` | CMake | 빌드 설정 (라이브러리, 컴파일 옵션) | 거의 없음 |
| `build_lidar.sh` | Shell | 빌드 자동화 (cmake + make) | 거의 없음 |
| `build/` | 폴더 | 컴파일 결과물 저장 | 자동 생성됨 |

---

## 📦 구성 요약

### 🧩 네트워크 구성

```
┌────────────────────────────────────────────────┐
│ LiDAR (192.168.123.120)                        │
│  ├─ UDP 56300 → 포인트클라우드 데이터                │
│  ├─ UDP 56100 → 명령 수신 (제어)                   │
│  └─ 멀티캐스트 주소: 224.1.1.5                     │
└────────────────────────────────────────────────┘
                      │
                      │ (유선 연결)
                      ▼
┌────────────────────────────────────────────────┐
│ Jetson Orin NX                                 │
│  ├─ 192.168.123.164 (LiDAR 전용 LAN)            │
│  ├─ 10.40.100.143 (WiFi, Mac 연결)              │
│  ├─ SDK 포트: 56101 / 56301 / ...               │
│  └─ LiDAR 데이터 → Mac으로 UDP 전송                │
└────────────────────────────────────────────────┘
                      │
                      │ (WiFi)
                      ▼
┌────────────────────────────────────────────────┐
│ Mac (10.40.100.105 예시)                        │
│  ├─ 8888 포트 수신                               │
│  └─ lidar_viewer.py로 시각화                     │
└────────────────────────────────────────────────┘
```

---

## ⚙️ 네트워크 설정

`g1_mid360_config.json` 파일의 설정에 따라 LiDAR ↔ Jetson 통신이 구성됩니다.

```json
"lidar_net_info": {
  "cmd_data_port": 56100,
  "point_data_port": 56300
},
"host_net_info": [
  {
    "host_ip": "192.168.123.164",
    "multicast_ip": "224.1.1.5",
    "point_data_port": 56301
  }
]
```

- **LiDAR IP (192.168.123.120)**
  → 명령을 받을 주소 (Jetson이 접근)
- **Jetson IP (192.168.123.164)**
  → 데이터를 받을 호스트 주소
- **멀티캐스트 주소 (224.1.1.5)**
  → LiDAR가 데이터를 방송하는 그룹 주소
- **UDP 포트 (56300 / 56301)**
  → 포인트클라우드 데이터 송신/수신 포트

💡 Jetson은 LiDAR에 "Normal 모드로 전환하라"고 명령(SetLivoxLidarWorkMode)을 보내고,
LiDAR는 224.1.1.5:56300으로 포인트클라우드를 계속 전송합니다.

---

## 🔨 빌드 방법

C++ 코드를 수정하거나 처음 사용할 때 빌드가 필요합니다.

### 방법 1: 자동 빌드 스크립트 (권장)

```bash
cd /home/unitree/AIM/LiDAR
./build_lidar.sh
```

**자동으로 수행되는 작업:**
1. `build/` 폴더 생성
2. CMake 설정 (`cmake ..`)
3. 컴파일 (`make`)
4. 실행 방법 안내 출력

### 방법 2: 수동 빌드

```bash
cd /home/unitree/AIM/LiDAR
mkdir -p build
cd build
cmake ..
make
```

**빌드 성공 확인:**
```bash
ls -lh build/g1_lidar_stream
# 출력: -rwxrwxr-x 1 unitree unitree 15K ... g1_lidar_stream
```

### 다시 빌드가 필요한 경우

- `g1_lidar_stream.cpp` 수정
- `CMakeLists.txt` 수정
- `build/` 폴더 삭제 후

### 빌드 불필요한 경우

- `g1_mid360_config.json` 수정 (런타임 설정)
- `lidar_viewer.py` 수정 (Python은 컴파일 없음)
- Mac IP 변경 (실행 시 인자로 전달)

---

## 🚀 실행 순서

### 1️⃣ Mac에서 Jetson IP 확인

Mac 터미널에서 Jetson이 속한 같은 대역(10.40.100.x)을 찾습니다.

```bash
ifconfig | grep "inet " | grep -v 127.0.0.1
```

결과 예시:

```
inet 10.40.100.105  netmask 0xffffff00  broadcast 10.40.100.255
```

→ 이 주소(10.40.100.105)를 Jetson 실행 명령에 사용합니다.

---

### 2️⃣ Jetson에서 LiDAR 스트리밍 실행

```bash
./build/g1_lidar_stream g1_mid360_config.json 10.40.100.105 8888
```

- `g1_mid360_config.json` → 네트워크 설정 파일
- `10.40.100.105` → 데이터를 받을 Mac IP
- `8888` → UDP 전송 포트

Jetson은 LiDAR로부터 받은 포인트클라우드를
Mac의 10.40.100.105:8888로 실시간 전송합니다.

---

### 3️⃣ Mac에서 실시간 뷰어 실행

```bash
python lidar_viewer.py
```

- UDP 8888 포트를 열어 Jetson에서 오는 데이터를 수신
- matplotlib 3D로 실시간 시각화
- LiDAR가 거꾸로 달린 경우 FLIP_X/Y/Z 옵션으로 축 반전 가능

---

## 🔧 상세 설정

### C++ 스트리밍 프로그램 (g1_lidar_stream.cpp)

**주요 기능:**

1. **Livox SDK 초기화**
   - `g1_mid360_config.json` 파일 로드
   - LiDAR 장치 검색 및 연결

2. **포인트 클라우드 콜백**
   ```cpp
   void PointCloudCallback(uint32_t handle, const uint8_t dev_type,
                          LivoxLidarEthernetPacket* data, void* client_data)
   ```
   - LiDAR 데이터 수신 시 자동 호출
   - (0,0,0) 무효 포인트 필터링
   - mm → m 단위 변환
   - UDP로 Mac에 전송

3. **데이터 구조 (13 bytes, packed)**
   ```cpp
   struct __attribute__((packed)) SimplePoint {
       float x, y, z;      // 12 bytes (각 4 bytes)
       uint8_t intensity;  // 1 byte
   };
   ```

4. **전송 통계**
   - 100 프레임마다 통계 출력
   - 전송된 포인트 수, 바이트 수

### Python 뷰어 설정 (lidar_viewer.py)

**커스터마이징 옵션:**

```python
# 좌표 변환 (LiDAR 방향 보정)
FLIP_X = False  # X축 반전
FLIP_Y = True   # Y축 반전 (일반적)
FLIP_Z = True   # Z축 반전 (거꾸로 장착 시)

# 성능 설정
max_points = 30000        # 최대 표시 포인트 수
clear_interval = 200      # 버퍼 초기화 주기 (프레임)

# 거리 필터
MAX_RANGE = 10.0          # 최대 거리 (미터)
MIN_RANGE = 0.1           # 최소 거리 (미터)
```

**축 반전 가이드:**
- 시각화가 뒤집혀 보이면 FLIP 옵션 조정
- LiDAR 장착 방향에 따라 달라짐
- 여러 조합을 시도해보세요

**성능 튜닝:**
- `max_points` ↓ → 빠른 렌더링, 적은 포인트
- `clear_interval` ↓ → 최신 데이터만, 깨끗한 화면
- `clear_interval` ↑ → 포인트 누적, 밀도 높은 클라우드

---

## 🧪 네트워크 연결 테스트

시각화가 안 보일 경우 아래 단계로 점검합니다:

```bash
# Mac 방화벽 상태 확인
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate

# 방화벽 끄기 (일시적으로)
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --setglobalstate off
```

UDP 통신이 되는지 간단히 확인하려면:

```bash
nc -ul 8888
```

→ 깨진 문자(바이너리 데이터)가 계속 들어오면 Jetson ↔ Mac UDP 연결 성공 ✅

---

## 🧠 참고: 통신 구조 이해하기

| 구분 | IP/주소 | 포트 | 방향 | 설명 |
|------|---------|------|------|------|
| LiDAR | 192.168.123.120 | 56300 | → | 포인트클라우드 전송 (UDP) |
| Jetson | 192.168.123.164 | 56301 | ← | LiDAR 데이터 수신 |
| 멀티캐스트 | 224.1.1.5 | - | ↔ | 여러 장치가 동시에 수신 가능 |
| Jetson → Mac | 10.40.100.143 → 10.40.100.105 | 8888 | → | Jetson이 Mac으로 데이터 재전송 |

---

## 💡 추가 팁

- **LiDAR 연결 확인**:

```bash
ping 192.168.123.120
```

- **Jetson이 LiDAR 포트를 열고 있는지 확인**:

```bash
sudo netstat -unlp | grep 563
```

- **포인트 스트리밍 로그 확인**:

```
전송 #100: 96 포인트, 1248 바이트
```

---

## 🧾 요약

| 단계 | 역할 | 명령 |
|------|------|------|
| ① | Mac IP 확인 | `ifconfig` |
| ② | Jetson 스트리밍 실행 | `./build/g1_lidar_stream g1_mid360_config.json 10.40.100.105 8888` |
| ③ | Mac 뷰어 실행 | `python lidar_viewer.py` |
| ④ | 안 될 때 점검 | 방화벽 / `nc -ul 8888` |

---

## 📘 개념 정리 (간단히)

| 개념 | 설명 |
|------|------|
| LiDAR IP (192.168.123.120) | 명령을 받을 대상 주소 |
| UDP 포트 (56300/56301) | 데이터를 송수신하는 통로 |
| 멀티캐스트 (224.1.1.5) | 여러 장치에 동시에 데이터 방송 |
| UDP 프로토콜 | 빠르고 실시간, 약간의 손실은 허용 |
| TCP와 차이점 | 확인 응답이 없어 속도 빠름 (LiDAR, 영상 등에 적합) |

---

## ❗ 트러블슈팅

### 문제 1: 빌드 실패

**증상:**
```
fatal error: livox_lidar_def.h: No such file or directory
```

**해결:**
- Livox SDK2가 설치되지 않음
- 설치: [Livox SDK2 GitHub](https://github.com/Livox-SDK/Livox-SDK2)

### 문제 2: Mac에서 데이터가 안 보임

**점검 순서:**

1. **Mac IP 확인**
   ```bash
   ifconfig | grep "inet " | grep -v 127.0.0.1
   # Jetson 실행 시 올바른 IP 사용했는지 확인
   ```

2. **방화벽 확인**
   ```bash
   sudo /usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate
   # "enabled"면 일시적으로 끄기
   ```

3. **UDP 수신 테스트**
   ```bash
   nc -ul 8888
   # 바이너리 데이터가 들어오면 네트워크 OK
   ```

4. **Jetson 로그 확인**
   ```
   "LiDAR 연결: S/N 47MDLCD0020008"  # 연결 성공
   "전송 #100: 96 포인트, 1248 바이트"  # 전송 중
   ```

### 문제 3: LiDAR가 연결 안 됨

**점검:**

1. **네트워크 인터페이스**
   ```bash
   ip addr show | grep 192.168.123
   # 192.168.123.164가 있어야 함
   ```

2. **LiDAR ping 확인**
   ```bash
   ping 192.168.123.120
   # 응답 있어야 함
   ```

3. **방화벽 포트**
   ```bash
   sudo netstat -unlp | grep 563
   # 56301, 56100 등 포트가 열려있어야 함
   ```

### 문제 4: 시각화가 거꾸로 보임

**해결:**
- `lidar_viewer.py` 파일에서 FLIP 옵션 조정
- 일반적으로 `FLIP_Y=True`, `FLIP_Z=True`

### 문제 5: 느린 성능 / 렉

**해결:**
- `lidar_viewer.py`에서 `max_points` 값 줄이기 (30000 → 10000)
- `clear_interval` 값 줄이기 (200 → 100)

### 문제 6: "SimplePoint 구조체 크기" 경고

**증상:**
```
SimplePoint 구조체 크기: 16 bytes (기대값: 13)
```

**해결:**
- `__attribute__((packed))`가 빠졌을 수 있음
- 다시 빌드: `./build_lidar.sh`

---

## 📚 참고 자료

### 공식 문서
- [Livox SDK2 GitHub](https://github.com/Livox-SDK/Livox-SDK2)
- [Livox Mid-360 매뉴얼](https://www.livoxtech.com/mid-360/downloads)
- [Unitree G1 Documentation](https://support.unitree.com/)

### 관련 개념
- **LiDAR**: Light Detection and Ranging (레이저 기반 거리 측정)
- **Point Cloud**: 3D 공간의 점들의 집합
- **UDP Multicast**: 여러 수신자에게 동시 데이터 전송
- **Livox SDK2**: Livox LiDAR 제어 및 데이터 수신 라이브러리

### 네트워크 포트 참조

| 포트 | 프로토콜 | 용도 |
|------|----------|------|
| 56100 | UDP | 명령 데이터 (LiDAR 제어) |
| 56300 | UDP | 포인트 클라우드 데이터 (송신) |
| 56301 | UDP | 포인트 클라우드 데이터 (수신) |
| 8888 | UDP | Jetson → Mac 스트리밍 |

### 데이터 포맷

**SimplePoint 구조체 (13 bytes):**
```
Offset | Type    | Name      | Size
-------|---------|-----------|------
0      | float   | x         | 4
4      | float   | y         | 4
8      | float   | z         | 4
12     | uint8_t | intensity | 1
-------|---------|-----------|------
Total: 13 bytes (packed, no padding)
```

---

## 🧭 결론

LiDAR는 192.168.123.120 주소로 Jetson의 명령을 받고,
224.1.1.5:56300으로 포인트 클라우드를 UDP로 방송합니다.
Jetson은 이를 56301 포트에서 받아 Mac(10.40.100.105:8888)으로 재전송하며,
Mac의 Python 뷰어는 이를 3D로 시각화합니다.

---

Made with 💡 by AIM Robotics
