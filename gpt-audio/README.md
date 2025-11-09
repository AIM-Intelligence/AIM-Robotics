# G1 Realtime Audio Chat

OpenAI Realtime API를 사용한 Unitree G1 음성 대화 시스템

## 📁 파일 구성

### ✅ `g1_realtime_chat_external.py` (권장)
**외부 USB 마이크/스피커 사용 - 안정적**

**특징:**
- ALSA를 직접 제어하여 안정적인 재생
- 하드웨어 재생 상태 모니터링 (`/proc/asound`)
- Echo 피드백 완벽 제거
- 부드러운 오디오 재생 보장
- EAGAIN/부분 쓰기 완벽 처리

**필요 장비:**
- USB 마이크 (예: ABKO N550)
- USB 스피커 (예: Fenda V720)

**실행:**
```bash
python3 g1_realtime_chat_external.py
```

---

### ⚠️ `g1_realtime_chat_dds.py` (실험적)
**G1 내장 스피커 사용 - 실험적**

**특징:**
- Unitree DDS/AudioClient 사용
- 외부 하드웨어 불필요
- 재생 상태 확인 불가능
- 간헐적 끊김 현상 있음

**실행:**
```bash
python3 g1_realtime_chat_dds.py
```

---

## 🎯 시스템 프롬프트 커스터마이징

시스템 프롬프트는 `prompts.py` 파일에서 관리됩니다.

### 사용 가능한 프롬프트

- **DEFAULT** - 기본 도우미
- **FRIENDLY** - 친근한 친구
- **EXPERT** - 전문가 어시스턴트
- **KOREAN_TUTOR** - 한국어 튜터
- **CODING_MENTOR** - 코딩 멘토
- **G1_ROBOT** - G1 로봇 어시스턴트
- **G1_ROBOT_KR** - G1 로봇 어시스턴트 (한국어)

### 프롬프트 변경 방법

**스크립트 파일을 열어서 직접 수정:**

`g1_realtime_chat_external.py` 또는 `g1_realtime_chat_dds.py`:

```python
# System prompt selection
# 옵션: "DEFAULT", "FRIENDLY", "EXPERT", "KOREAN_TUTOR", "CODING_MENTOR", "G1_ROBOT", "G1_ROBOT_KR"
SYSTEM_PROMPT_NAME = "G1_ROBOT"  # ← 원하는 프롬프트로 변경
```

### 커스텀 프롬프트 추가

`prompts.py` 파일을 열고 새로운 프롬프트 변수를 추가:

```python
# prompts.py
MY_CUSTOM = """Your custom system prompt here.
Add your instructions for the AI assistant."""

# 저장 후 스크립트에서 사용
SYSTEM_PROMPT_NAME = "MY_CUSTOM"
```

---

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
OPENAI_REALTIME_VOICE=verse
```

---

## 🔧 설치

### 필수 패키지
```bash
pip install pyalsaaudio websockets python-dotenv
```

### G1 내장 스피커 사용 시 추가
```bash
pip install unitree_sdk2_python
```

---

## 💡 사용 팁

### 1. 마이크/스피커 확인
```bash
# 마이크 확인
arecord -l

# 스피커 확인
aplay -l
```

### 2. 장치 패턴 커스터마이징
스크립트 내에서 다음 변수를 수정:
```python
MIC_NAME_PATTERNS = ["N550", "ABKO", "USB", "Your_Mic_Name"]
SPEAKER_NAME_PATTERNS = ["V720", "Fenda", "USB", "Your_Speaker_Name"]
```

### 3. 오디오 품질 조정
```python
# 프리버퍼 크기 (ms) - 더 크면 안정적, 더 작으면 저지연
PREBUFFER_MS = 250

# 청크 크기
MIC_CHUNK_FRAMES = 2400      # 100ms
SPEAKER_CHUNK_FRAMES = 1200  # 50ms
```

---

## 🎤 시스템 프롬프트 예시 모음

`prompts.py` 파일에서 확인할 수 있는 프롬프트들:

### DEFAULT
```
You are a helpful AI assistant having a voice conversation with a user.
Be concise, natural, and conversational in your responses.
```

### FRIENDLY
```
You are a friendly companion having a casual voice chat.
Be warm, empathetic, and use natural conversational language.
Ask follow-up questions to keep the conversation engaging.
Keep responses concise and natural for voice conversation.
```

### EXPERT
```
You are an expert technical assistant.
Provide detailed, accurate information while remaining clear and concise.
Use examples when helpful.
Explain complex concepts in simple terms for voice conversation.
```

### KOREAN_TUTOR
```
You are a patient Korean language tutor.
Help users practice Korean conversation.
Correct mistakes gently and explain grammar when needed.
Keep explanations simple and encourage practice.
```

### CODING_MENTOR
```
You are an experienced coding mentor.
Help with programming questions and code reviews.
Explain concepts clearly with practical examples.
Encourage best practices and clean code.
```

### G1_ROBOT_KR
```
당신은 Unitree G1 로봇의 AI 어시스턴트입니다.
로봇 제어를 도울 수 있고, 질문에 답하며, 대화를 나눌 수 있습니다.
친절하고 도움이 되며, 때때로 로봇의 특성을 언급하세요.
음성 상호작용을 위해 간결하게 응답하세요.
```

---

## 📊 문제 해결

### 소리가 끊긴다
→ `PREBUFFER_MS` 값을 늘리세요 (250 → 500)

### 마이크를 찾지 못한다
→ `arecord -l`로 확인 후 `MIC_NAME_PATTERNS`에 추가

### Echo 피드백이 있다
→ USB 외부 스피커 사용 권장 (`g1_realtime_chat_external.py`)

### 두 번째 응답부터 소리가 안 난다
→ `g1_realtime_chat_external.py` 사용 (DDS 버전 문제)

---

## 🎯 권장사항

안정적인 음성 대화를 위해서는 **`g1_realtime_chat_external.py` + USB 장비** 사용을 강력히 권장합니다.

---

## 📝 라이센스

이 프로젝트는 Unitree G1 SDK와 OpenAI Realtime API를 사용합니다.
각각의 라이센스 조항을 준수하세요.
