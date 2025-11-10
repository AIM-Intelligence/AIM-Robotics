# G1 Realtime Multimodal Chat

OpenAI Realtime API를 사용한 Unitree G1 음성 + 비전 통합 시스템

## 🎯 주요 기능

- **음성 대화**: USB 마이크로 말하고, USB 스피커로 응답 듣기
- **비전 인식**: RealSense D435i 카메라로 주변 환경 인식
- **통합 대화**: 음성과 시각 정보를 자연스럽게 통합한 대화

## 📁 파일 구성

```
gpt-multimodal/
├── g1_realtime_multimodal.py          # 기본 멀티모달 스크립트 (음성+시각)
├── g1_realtime_multimodal_tool.py     # 팔 제어 기능 추가 (음성 명령)
├── g1_realtime_multimodal_tool_v2.py  # 자율 시각 반응 (명령 없이 제스처 인식)
├── config.py                           # 설정 (카메라, 오디오 등)
├── prompts.py                          # 시스템 프롬프트
├── requirements.txt                    # 의존성
└── README.md                           # 이 파일
```

## 🔧 설치

### 필수 패키지

```bash
pip install -r requirements.txt
```

### 하드웨어 요구사항

- **USB 마이크** (예: ABKO N550)
- **USB 스피커** (예: Fenda V720)
- **Intel RealSense D435i** 카메라

## ⚙️ 환경 설정

### 필수 환경변수

`.env` 파일에 다음을 추가:

```bash
OPENAI_API_KEY=your_api_key_here
```

### 선택적 환경변수

```bash
# OpenAI 모델 (기본값: gpt-realtime)
OPENAI_REALTIME_MODEL=gpt-realtime

# 음성 선택 (기본값: cedar)
# 옵션: alloy, ash, ballad, coral, echo, sage, shimmer, verse, marin, cedar
OPENAI_REALTIME_VOICE=cedar
```

## 🎯 시스템 프롬프트 커스터마이징

시스템 프롬프트는 `prompts.py` 파일에서 관리됩니다.

### 사용 가능한 프롬프트

- **MULTIMODAL** - 기본 멀티모달 어시스턴트
- **MULTIMODAL_KR** - 멀티모달 어시스턴트 (한국어)
- **G1_VISION_ROBOT** - G1 비전 로봇 어시스턴트
- **G1_VISION_ROBOT_KR** - G1 비전 로봇 어시스턴트 (한국어)
- **FRIENDLY** - 친근한 친구
- **EXPERT** - 전문가

### 프롬프트 변경 방법

`config.py` 파일을 열어서 수정:

```python
# System Prompt
SYSTEM_PROMPT_NAME = "MULTIMODAL"  # ← 원하는 프롬프트로 변경
```

### 커스텀 프롬프트 추가

`prompts.py` 파일에 새로운 프롬프트 변수 추가:

```python
# prompts.py
MY_CUSTOM = """Your custom multimodal prompt here.
You can see and hear..."""

# 저장 후 config.py에서 사용
SYSTEM_PROMPT_NAME = "MY_CUSTOM"
```

## 🎥 카메라 설정

### 이미지 전송 간격

`config.py`에서 조정:

```python
IMAGE_SEND_INTERVAL = 10.0  # 10초마다 이미지 전송 (기본값)
```

**권장 간격**:
- 일반 대화: 10-15초
- 탐색/내비게이션: 5-7초
- 비용 절감: 20-30초

### 이미지 품질

```python
JPEG_QUALITY = 75  # 0-100 (낮을수록 비용 절감)
```

### 비전 기능 끄기

```python
SEND_IMAGES = False  # True로 설정하면 카메라 사용
```

## 🚀 실행

### 버전별 실행 방법

**기본 멀티모달 (음성+시각)**
```bash
python3 g1_realtime_multimodal.py
```

**팔 제어 + 음성 명령**
```bash
python3 g1_realtime_multimodal_tool.py
```
- 음성 명령으로 제스처 실행 ("안녕!", "사랑해" 등)
- AI가 대화 맥락에서 자율적으로 제스처 판단

**자율 시각 반응 (V2) - NEW!**
```bash
python3 g1_realtime_multimodal_tool_v2.py
```
- 음성 명령 없이 시각 정보만으로 자율 반응
- 매우 확실한 제스처만 인식 (악수, 하트, 인사 등)
- 애매한 상황에서는 침묵

## 💡 사용 팁

### 1. 오디오 장치 확인

```bash
# 마이크 확인
arecord -l

# 스피커 확인
aplay -l
```

### 2. RealSense 카메라 확인

```bash
# RealSense 뷰어 실행
realsense-viewer
```

### 3. 장치 패턴 커스터마이징

`config.py`에서 다음 변수 수정:

```python
MIC_NAME_PATTERNS = ["N550", "ABKO", "USB", "Your_Mic_Name"]
SPEAKER_NAME_PATTERNS = ["V720", "Fenda", "USB", "Your_Speaker_Name"]
```

### 4. 오디오 품질 조정

```python
# 프리버퍼 크기 (ms) - 더 크면 안정적, 더 작으면 저지연
PREBUFFER_MS = 250

# 청크 크기
MIC_CHUNK_FRAMES = 2400      # 100ms
SPEAKER_CHUNK_FRAMES = 1200  # 50ms
```

## 📊 비용 정보

### 시간당 예상 비용 (2025년 기준)

**이미지 전송 간격별**:

- **5초 간격** (~720 이미지/시간):
  - 오디오 입력: $60/시간
  - 오디오 출력: $60/시간
  - 이미지: ~$2.50/시간
  - **총: ~$122.50/시간**

- **10초 간격** (~360 이미지/시간):
  - 오디오 입력: $60/시간
  - 오디오 출력: $60/시간
  - 이미지: ~$1.25/시간
  - **총: ~$121.25/시간**

- **20초 간격** (~180 이미지/시간):
  - 오디오 입력: $60/시간
  - 오디오 출력: $60/시간
  - 이미지: ~$0.65/시간
  - **총: ~$120.65/시간**

**비용 절감 팁**:
- 이미지 전송 간격을 늘리기 (10→20초)
- JPEG 품질 낮추기 (75→50)
- 필요할 때만 비전 활성화

## 📊 문제 해결

### 소리가 끊긴다
→ `config.py`에서 `PREBUFFER_MS` 값을 늘리세요 (250 → 500)

### 마이크를 찾지 못한다
→ `arecord -l`로 확인 후 `MIC_NAME_PATTERNS`에 추가

### RealSense 카메라가 인식되지 않는다
→ `realsense-viewer`로 카메라 작동 확인
→ USB 3.0 포트에 연결되어 있는지 확인

### 이미지가 전송되지 않는다
→ `config.py`에서 `SEND_IMAGES = True` 확인
→ RealSense 초기화 성공 메시지 확인

### Echo 피드백이 있다
→ USB 외부 스피커 사용 (내장 스피커 대신)
→ 마이크와 스피커 거리 충분히 확보

## 🎯 권장사항

안정적인 멀티모달 대화를 위한 권장 설정:

- **오디오**: USB 외부 마이크/스피커
- **비전**: RealSense D435i
- **이미지 간격**: 10초
- **JPEG 품질**: 75
- **프롬프트**: `MULTIMODAL_KR` 또는 `G1_VISION_ROBOT_KR`

## 🔄 업데이트 내역

### v2.0.0 (2025-01-10)
- **NEW**: 자율 시각 반응 모드 추가 (g1_realtime_multimodal_tool_v2.py)
  - 음성 명령 없이 시각 정보만으로 제스처 인식
  - 매우 확실한 상황에서만 자율 반응
  - 제스처 + 음성 동시 실행 문제 해결
- 마이크 재오픈 버그 수정 (response.done 중복 처리)
- 시스템 프롬프트 개선 (영어/한국어 통일)

### v1.1.0 (2025-01-10)
- G1 팔 제어 기능 추가 (g1_realtime_multimodal_tool.py)
- Function calling 기반 제스처 실행
- 자동 release 기능 (0.5초 후)
- 비블로킹 제스처 실행

### v1.0.0 (2025-01-10)
- 초기 릴리스
- OpenAI Realtime API 멀티모달 지원
- RealSense D435i 통합
- USB 오디오 장치 지원
- 시스템 프롬프트 커스터마이징

## 📝 라이센스

이 프로젝트는 Unitree G1 SDK, Intel RealSense SDK, OpenAI Realtime API를 사용합니다.
각각의 라이센스 조항을 준수하세요.

## 🆘 지원

문제가 발생하면 다음을 확인하세요:
1. 모든 하드웨어가 올바르게 연결되어 있는지
2. `.env` 파일에 `OPENAI_API_KEY`가 설정되어 있는지
3. 필수 패키지가 모두 설치되어 있는지
4. USB 장치와 RealSense가 `arecord -l`, `aplay -l`, `realsense-viewer`로 인식되는지
