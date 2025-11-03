# 전체 파이프라인 프로파일링 비교: Python vs C++

**날짜**: 2025-11-03
**측정 방법**: 실제 LiDAR 데이터 (Mid-360, 2000 pps)
**측정 기간**: 각 30초씩

---

## Executive Summary

### 프레임당 처리 시간 비교 (203.2 packets/frame 기준)

| 단계 | Python | C++ | 개선율 | 비중 (Python) | 비중 (C++) |
|------|--------|-----|--------|---------------|------------|
| **Phase 1 (Protocol)** | 20.67 ms | 7.68 ms | **2.69x 빠름** | 37.6% | 19.2% |
| **Phase 2 (Frame)** | 5.16 ms | 3.25 ms | **1.59x 빠름** | 9.4% | 8.1% |
| **SLAM (KISS-ICP)** | 29.13 ms | 29.13 ms | 동일 (이미 C++) | 53.0% | 72.7% |
| **─────────────** | ───── | ───── | ──────── | ─────── | ─────── |
| **TOTAL** | **54.96 ms** | **40.06 ms** | **1.37x 빠름** | 100% | 100% |

### 핵심 결과

✅ **Phase 1 + Phase 2 최적화로 전체 처리 시간 14.9ms 단축** (54.96ms → 40.06ms)
✅ **전체 파이프라인 1.37x 속도 향상**
⚠️ **SLAM이 전체 시간의 72.7%를 차지** (C++ 적용 후)

---

## 상세 측정 결과

### 1. Python 백엔드 (Full Python)

#### 패킷당 처리 시간

```
Phase 1: Protocol Parser (Python)
  평균:    101.73 μs/packet
  중앙값:   84.42 μs/packet
  표준편차:  255.04 μs
  95백분위:  201.90 μs
  측정수:   59,536 packets

Phase 2: Frame Builder (Python)
  평균:     25.38 μs/packet
  중앙값:    17.38 μs/packet
  표준편차:   105.42 μs
  95백분위:   49.31 μs
  측정수:    59,536 packets
```

#### 프레임당 처리 시간

```
SLAM: KISS-ICP (C++ via pybind11)
  평균:     29.13 ms/frame
  중앙값:    25.45 ms/frame
  표준편차:   10.90 ms
  95백분위:   52.92 ms
  측정수:    293 frames
```

#### 전체 파이프라인 (203.2 packets/frame 기준)

```
Phase 1 (Protocol):  20.67 ms/frame  (37.6%)
Phase 2 (Frame):      5.16 ms/frame  ( 9.4%)
SLAM (KISS-ICP):     29.13 ms/frame  (53.0%)
──────────────────────────────────────────
TOTAL:               54.96 ms/frame

이론상 최대 FPS: 18.2 fps
실제 FPS:         9.8 fps
```

---

### 2. C++ 백엔드 (Phase 1 + Phase 2 C++)

#### 패킷당 처리 시간

```
Phase 1: Protocol Parser (C++)
  평균:     37.77 μs/packet  ← Python 대비 2.69x 빠름
  중앙값:    34.21 μs/packet
  표준편차:   24.12 μs
  95백분위:   74.04 μs
  측정수:    59,927 packets

Phase 2: Frame Builder (C++)
  평균:     16.01 μs/packet  ← Python 대비 1.59x 빠름
  중앙값:    12.58 μs/packet
  표준편차:   17.93 μs
  95백분위:   31.65 μs
  측정수:    59,927 packets
```

#### 전체 파이프라인 (203.2 packets/frame 기준)

```
Phase 1 (Protocol):   7.68 ms/frame  (19.2%)
Phase 2 (Frame):      3.25 ms/frame  ( 8.1%)
SLAM (KISS-ICP):     29.13 ms/frame  (72.7%)  ← 동일 (이미 C++)
──────────────────────────────────────────
TOTAL:               40.06 ms/frame

이론상 최대 FPS: 25.0 fps
```

---

## 단계별 개선 효과

### Phase 1: Protocol Parser

```
Python:  101.73 μs/packet  (20.67 ms/frame)
C++:      37.77 μs/packet  ( 7.68 ms/frame)
──────────────────────────────────────────
개선:     63.96 μs/packet  (12.99 ms/frame)
속도:     2.69x 빠름
절감:     37.6% → 19.2%로 감소
```

**분석**:
- CRC 검증, 바이트 파싱, 구조체 변환 등이 C++로 최적화
- 가장 큰 개선 효과 (12.99ms 절감)
- 전체 파이프라인에서 차지하는 비중이 37.6% → 19.2%로 크게 감소

---

### Phase 2: Frame Builder

```
Python:  25.38 μs/packet  (5.16 ms/frame)
C++:     16.01 μs/packet  (3.25 ms/frame)
──────────────────────────────────────────
개선:     9.37 μs/packet  (1.91 ms/frame)
속도:     1.59x 빠름
절감:     9.4% → 8.1%로 감소
```

**분석**:
- 시간 기반 프레임 경계 판단, 포인트 누적 최적화
- 중간 정도의 개선 효과 (1.91ms 절감)
- 상대적으로 간단한 로직이라 개선 폭이 Protocol보다 작음

---

### SLAM: KISS-ICP

```
Python backend:  29.13 ms/frame  (53.0% of total)
C++ backend:     29.13 ms/frame  (72.7% of total)
──────────────────────────────────────────
개선:     없음 (이미 C++로 구현됨)
```

**분석**:
- KISS-ICP 라이브러리는 이미 C++로 구현되어 pybind11을 통해 호출
- Python/C++ 백엔드 선택과 무관하게 동일한 시간 소요
- Phase 1, 2가 빨라지면서 상대적 비중이 53.0% → 72.7%로 증가

---

## 전체 파이프라인 비교

### 시각적 비교

```
Python 전체 파이프라인 (54.96 ms/frame):
  [████████████████████ Protocol 20.67ms (37.6%)]
  [█████ Frame 5.16ms (9.4%)]
  [██████████████████████████ SLAM 29.13ms (53.0%)]

C++ 전체 파이프라인 (40.06 ms/frame):
  [████████ Protocol 7.68ms (19.2%)]
  [███ Frame 3.25ms (8.1%)]
  [██████████████████████████████ SLAM 29.13ms (72.7%)]

절감:
  [████████████ 12.99ms] Protocol 개선
  [██ 1.91ms] Frame 개선
  ───────────────────────────
  총 14.9ms 절감 (27.1% 감소)
```

### 성능 지표

| 지표 | Python | C++ | 개선 |
|------|--------|-----|------|
| **프레임당 처리 시간** | 54.96 ms | 40.06 ms | **14.9 ms 감소** |
| **이론상 최대 FPS** | 18.2 fps | 25.0 fps | **+37.4%** |
| **Protocol+Frame 시간** | 25.83 ms | 10.93 ms | **2.36x 빠름** |
| **SLAM 비중** | 53.0% | 72.7% | +19.7%p |

---

## 실제 성능에 미치는 영향

### CPU 사용률 추정

**가정**: 10 fps로 SLAM 실행 시

```
Python 백엔드:
  CPU 시간 = 54.96 ms/frame × 10 fps = 549.6 ms/s = 54.96% CPU

C++ 백엔드:
  CPU 시간 = 40.06 ms/frame × 10 fps = 400.6 ms/s = 40.06% CPU

절감: 14.9% CPU
```

### 실제 FPS 향상 (병목 제거 시)

현재 실제 FPS (9.8 fps)는 이론상 최대치(18.2 fps)보다 낮습니다. 이는:
1. UDP 수신 대기 시간
2. Python GIL (Global Interpreter Lock)
3. 기타 시스템 오버헤드

C++ 최적화 적용 시 예상 FPS:
- 이론상 최대: 25.0 fps
- 실제 예상: 13-15 fps (UDP/GIL 오버헤드 고려)
- 개선폭: +3-5 fps (33-51% 향상)

---

## 결론

### 요약

1. **Phase 1 (Protocol Parser)**
   - Python 101.73 μs → C++ 37.77 μs/packet
   - **2.69x 속도 향상, 12.99ms/frame 절감**
   - 가장 큰 개선 효과

2. **Phase 2 (Frame Builder)**
   - Python 25.38 μs → C++ 16.01 μs/packet
   - **1.59x 속도 향상, 1.91ms/frame 절감**
   - 중간 정도의 개선 효과

3. **전체 파이프라인**
   - Python 54.96 ms → C++ 40.06 ms/frame
   - **1.37x 속도 향상, 14.9ms/frame 절감**
   - CPU 사용률 ~15% 감소

4. **SLAM (KISS-ICP)**
   - 이미 C++로 구현되어 개선 없음
   - 전체 시간의 72.7% 차지 (병목)

### Phase 1과 Phase 2의 가치

**Phase 1 (Protocol Parser C++)**:
- ✅ **매우 유의미함**: 12.99ms 절감, 2.69x 속도 향상
- ✅ CPU 사용률 대폭 감소
- ✅ 프레임당 처리 시간의 37.6% → 19.2%로 감소

**Phase 2 (Frame Builder C++)**:
- ✅ **유의미함**: 1.91ms 절감, 1.59x 속도 향상
- ⚠️ Phase 1보다는 작은 개선 폭
- ✅ 프레임당 처리 시간의 9.4% → 8.1%로 감소

**Phase 1 + Phase 2 합산 효과**:
- ✅ **14.9ms 절감 (전체의 27.1%)**
- ✅ **2.36x 속도 향상** (Protocol+Frame 합계)
- ✅ **CPU 사용률 약 15% 감소**

### 최종 판단

**✅ Phase 1과 Phase 2는 모두 의미 있는 최적화입니다.**

SLAM이 가장 큰 병목(72.7%)이지만:
1. SLAM은 이미 C++로 최적화되어 있어 더 이상 개선 불가
2. Phase 1 + 2 최적화로 **전체 처리 시간 27% 감소**
3. **CPU 사용률 15% 감소**로 로봇 시스템의 다른 작업에 여유 확보
4. **실시간 처리 여유 증가** (더 높은 프레임률 지원 가능)

### Batch API의 추가 효과

현재 측정은 Single-packet 모드입니다. Batch API 적용 시:
- Phase 1: 추가 개선 여지 적음 (이미 최적화됨)
- Phase 2: 추가 1.5-2x 개선 가능 (Python/C++ 경계 오버헤드 감소)
- 예상 총 절감: ~17-18ms/frame

---

## 측정 조건

- **플랫폼**: Unitree G1 (Jetson ARM64)
- **LiDAR**: Livox Mid-360
- **패킷률**: ~2000 pps
- **프레임률**: 10 Hz (0.1초 주기)
- **패킷/프레임**: 203.2 packets
- **측정 시간**: 30초 (각각)
- **백엔드**: Python vs C++ (Phase 1 + 2)

---

**보고서 작성**: 2025-11-03
**프로파일링 스크립트**: `profile_pipeline.py`
