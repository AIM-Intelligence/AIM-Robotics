#!/usr/bin/env python3
# g1_realtime_chat_usb.py
# External USB mic/speaker on Unitree G1 + OpenAI Realtime
# - 24 kHz mono S16_LE end-to-end
# - Mutes mic while AI is speaking
# - Waits for *hardware* playback finish (/proc/asound/...) before re-enabling mic
# - Reopens speaker device on every new response (and on barge-in) to avoid SETUP state

import os, asyncio, json, base64, time, subprocess, re, glob
import websockets
import queue
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
import prompts

try:
    import alsaaudio
except ImportError:
    print("❌ pyalsaaudio가 없습니다. 설치:  pip install pyalsaaudio")
    raise

load_dotenv()

# ----------------- Config -----------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MODEL  = os.getenv("OPENAI_REALTIME_MODEL", "gpt-realtime")
VOICE  = os.getenv("OPENAI_REALTIME_VOICE", "cedar")

# System prompt selection
# 옵션: "DEFAULT", "FRIENDLY", "EXPERT", "KOREAN_TUTOR", "CODING_MENTOR", "G1_ROBOT", "G1_ROBOT_KR"
SYSTEM_PROMPT_NAME = "JEFFREY"  # ← 원하는 프롬프트로 변경

AUDIO_RATE     = 24000      # mic/speaker 모두 24kHz
AUDIO_CHANNELS = 1
S16LE_BYTES    = 2

MIC_CHUNK_FRAMES     = 2400  # 100ms @ 24k
SPEAKER_CHUNK_FRAMES = 1200  # 50ms @ 24k
PREBUFFER_MS         = 250   # 부드러운 시작을 위한 프리버퍼
PREBUFFER_BYTES      = int(AUDIO_RATE * S16LE_BYTES * PREBUFFER_MS / 1000)

MIC_NAME_PATTERNS     = ["N550", "ABKO", "USB", "Headset", "Microphone"]
SPEAKER_NAME_PATTERNS = ["V720", "Fenda", "USB", "Speaker", "Headphones"]

# ----------------- Load System Prompt -----------------
def load_system_prompt():
    """Get system prompt from prompts.py"""
    prompt = prompts.get_prompt(SYSTEM_PROMPT_NAME)
    print(f"✅ System prompt: {SYSTEM_PROMPT_NAME}")
    return prompt

# ----------------- Helpers -----------------
def find_usb_audio_device(patterns, device_type="input"):
    """Return (device_string, card_num:str, dev_num:str) or (None, None, None)"""
    cmd = 'arecord' if device_type == "input" else 'aplay'
    try:
        out = subprocess.check_output([cmd, '-l'], universal_newlines=True)
    except Exception as e:
        print(f"❌ {cmd} -l 실패: {e}")
        return None, None, None

    for line in out.splitlines():
        # e.g. "card 3: V720 [Fenda V720], device 0: USB Audio [USB Audio]"
        m = re.search(r'card (\d+):\s+(\S+)\s+\[([^\]]+)\].*device (\d+)', line)
        if not m: 
            continue
        card_num, card_id, card_name, dev_num = m.group(1), m.group(2), m.group(3), m.group(4)
        for p in patterns:
            if p in card_name or p in card_id:
                dev_str = f"plughw:CARD={card_id},DEV={dev_num}"
                return dev_str, card_num, dev_num
    return None, None, None

def list_status_paths(card_num: str, dev_num: str):
    # /proc/asound/card{card}/pcm{dev}p/sub*/status
    base = f"/proc/asound/card{card_num}/pcm{dev_num}p"
    return sorted(glob.glob(f"{base}/sub*/status"))

def speaker_is_playing(card_num: str, dev_num: str) -> bool:
    """RUNNING/DRAINING anywhere under sub*/status => playing"""
    for path in list_status_paths(card_num, dev_num):
        try:
            with open(path, "r") as f:
                s = f.read()
                if "state: RUNNING" in s or "state: DRAINING" in s:
                    return True
        except Exception:
            continue
    return False

# 스피커 오픈 파라미터(재오픈에 사용)
SPEAKER_PARAMS = {
    "device": None,  # set later
    "channels": AUDIO_CHANNELS,
    "rate": AUDIO_RATE,
    "format": alsaaudio.PCM_FORMAT_S16_LE,
    "periodsize": SPEAKER_CHUNK_FRAMES,
    "mode": alsaaudio.PCM_NONBLOCK,
}

def open_speaker():
    return alsaaudio.PCM(
        alsaaudio.PCM_PLAYBACK,
        SPEAKER_PARAMS["mode"],
        device=SPEAKER_PARAMS["device"],
        channels=SPEAKER_PARAMS["channels"],
        rate=SPEAKER_PARAMS["rate"],
        format=SPEAKER_PARAMS["format"],
        periodsize=SPEAKER_PARAMS["periodsize"],
    )

# ----------------- Main -----------------
async def main():
    assert OPENAI_API_KEY, "❌ OPENAI_API_KEY 환경변수를 설정하세요."

    # 1) 디바이스 탐색
    print("🔍 USB 입력(마이크) 탐색 중…")
    mic_device, mic_card, mic_dev = find_usb_audio_device(MIC_NAME_PATTERNS, "input")
    if not mic_device:
        print("❌ 마이크를 찾지 못했습니다. arecord -l로 장치 확인해주세요.")
        return
    print(f"   🎤 Mic -> {mic_device} (card{mic_card}/dev{mic_dev})")

    print("🔍 USB 출력(스피커) 탐색 중…")
    speaker_device, speaker_card, speaker_dev = find_usb_audio_device(SPEAKER_NAME_PATTERNS, "output")
    if not speaker_device:
        print("❌ 스피커를 찾지 못했습니다. aplay -l로 장치 확인해주세요.")
        return
    print(f"   🔊 Speaker -> {speaker_device} (card{speaker_card}/dev{speaker_dev})")

    # 2) 장치 오픈
    print("🎤 마이크 여는 중…")
    mic = alsaaudio.PCM(
        alsaaudio.PCM_CAPTURE,
        alsaaudio.PCM_NORMAL,
        device=mic_device,
        channels=AUDIO_CHANNELS,
        rate=AUDIO_RATE,
        format=alsaaudio.PCM_FORMAT_S16_LE,
        periodsize=MIC_CHUNK_FRAMES,
    )
    print("✅ 마이크 준비 완료")

    SPEAKER_PARAMS["device"] = speaker_device
    print("🔊 스피커 여는 중…")
    speaker = open_speaker()
    print("✅ 스피커 준비 완료 (non-blocking)")

    # 3) Load system prompt
    system_prompt = load_system_prompt()

    # 4) OpenAI Realtime 연결
    url = f"wss://api.openai.com/v1/realtime?model={MODEL}"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "OpenAI-Beta": "realtime=v1",
    }
    print("🔌 Realtime API 연결 중…")

    try:
        async with websockets.connect(url, extra_headers=headers, ping_timeout=10, close_timeout=5) as ws:
            print("✅ OpenAI Realtime 연결 완료")

            # 세션 설정 (with system prompt)
            await ws.send(json.dumps({
                "type": "session.update",
                "session": {
                    "modalities": ["audio", "text"],
                    "instructions": system_prompt,  # ★ System prompt added
                    "voice": VOICE,
                    "input_audio_format": "pcm16",
                    "output_audio_format": "pcm16",
                    "input_audio_transcription": {"model": "whisper-1"},
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": 0.5,
                        "prefix_padding_ms": 300,
                        "silence_duration_ms": 500
                    }
                }
            }))
            print("⚙️ 세션 구성 완료")

            print("\n" + "="*60)
            print("🎙️  REALTIME CHAT (USB mic & speaker)")
            print("="*60)
            print("말하면 인식 → 응답은 스피커로 재생")
            print("하드웨어 재생 종료 시점에 정확히 마이크 재개")
            print("Ctrl+C 로 종료")
            print("="*60 + "\n")

            # 4) 상태
            buffer_audio = bytearray()      # 스피커로 보낼 24k PCM 버퍼
            mic_enabled = True
            prebuffered = False
            playing = False
            is_running = True

            # (옵션) 송신된 프레임 타임라인 추적
            playback_queue = deque()  # (send_time, duration_sec)

            # 5) 마이크 스레드(블로킹 read → 큐)
            mic_queue = queue.Queue(maxsize=200)
            executor = ThreadPoolExecutor(max_workers=1)

            def mic_reader():
                while is_running:
                    try:
                        nframes, data = mic.read()  # returns frames, bytes
                        if nframes > 0:
                            try:
                                mic_queue.put(data, timeout=0.1)
                            except queue.Full:
                                pass
                    except Exception as e:
                        if is_running:
                            print(f"⚠️ Mic read error: {e}")
                        break

            executor.submit(mic_reader)

            # 6) 스피커 피더 (부분쓰기/EAGAIN 처리 + 프리버퍼)
            async def feeder():
                nonlocal playing, prebuffered, speaker
                FRAMES = SPEAKER_CHUNK_FRAMES
                BYTES_PER_CHUNK = FRAMES * S16LE_BYTES
                retry_chunk = None

                while is_running:
                    await asyncio.sleep(0)

                    if not prebuffered and not playing:
                        if len(buffer_audio) >= PREBUFFER_BYTES:
                            prebuffered = True
                            print("🔊 Prebuffer 완료 → 재생 시작")
                        else:
                            await asyncio.sleep(0.005)
                            continue

                    # 재시도 중 청크가 있으면 우선
                    if retry_chunk is not None:
                        chunk = retry_chunk
                        retry_chunk = None
                    elif len(buffer_audio) >= BYTES_PER_CHUNK:
                        chunk = bytes(buffer_audio[:BYTES_PER_CHUNK])
                        del buffer_audio[:BYTES_PER_CHUNK]
                    else:
                        await asyncio.sleep(0.004)
                        continue

                    try:
                        written_frames = speaker.write(chunk)  # returns frames written or 0(EAGAIN)
                        if written_frames <= 0:
                            # EAGAIN → 재시도
                            retry_chunk = chunk
                            await asyncio.sleep(0.01)
                            continue

                        written_bytes = written_frames * S16LE_BYTES
                        if written_bytes < len(chunk):
                            # 부분쓰기 → 남은 데이터 다시 버퍼 앞에
                            rest = chunk[written_bytes:]
                            buffer_audio[:0] = rest
                            await asyncio.sleep(0.005)
                        else:
                            # 전부 성공
                            playing = True
                            playback_queue.append((time.time(), FRAMES / AUDIO_RATE))
                            await asyncio.sleep(0.045)  # 50ms보다 살짝 짧게

                    except alsaaudio.ALSAAudioError as e:
                        # -11(EAGAIN) 포함
                        retry_chunk = chunk
                        await asyncio.sleep(0.01)
                    except Exception as e:
                        print(f"⚠️ Speaker write error: {e}")
                        await asyncio.sleep(0.05)

            # 7) 마이크 업링크 → Realtime
            async def mic_sender():
                nonlocal mic_enabled
                while is_running:
                    try:
                        if mic_enabled:
                            try:
                                data = mic_queue.get_nowait()
                                await ws.send(json.dumps({
                                    "type": "input_audio_buffer.append",
                                    "audio": base64.b64encode(data).decode("ascii"),
                                }))
                            except queue.Empty:
                                pass
                        else:
                            # 음소거 중엔 큐 비우기
                            try:
                                mic_queue.get_nowait()
                            except queue.Empty:
                                pass
                        await asyncio.sleep(0.008)
                    except Exception as e:
                        if is_running:
                            print(f"⚠️ Mic send error: {e}")
                        break

            # 8) 수신 루프
            async def receiver():
                nonlocal mic_enabled, prebuffered, playing, speaker
                while is_running:
                    try:
                        msg = json.loads(await ws.recv())
                        t = msg.get("type")

                        if t == "response.created":
                            # 새 응답 시작 → 스피커 초기화 + 마이크 음소거
                            buffer_audio.clear()
                            prebuffered = False
                            playing = False
                            # 이전 재생이 남아있을 수 있으므로 장치 *재오픈*
                            try:
                                try:
                                    speaker.close()
                                except Exception:
                                    pass
                                speaker = open_speaker()
                                print("🔁 Speaker reopen (new response)")
                            except Exception as e:
                                print(f"⚠️ Speaker reopen 실패: {e}")

                            if mic_enabled:
                                mic_enabled = False
                                print("🔇 Mic muted (AI speaking)")

                        elif t in ("response.output_audio.delta", "response.audio.delta"):
                            if mic_enabled:
                                mic_enabled = False
                                print("🔇 Mic muted (AI speaking)")

                            b64 = msg.get("delta") or msg.get("audio") or ""
                            if b64:
                                buffer_audio.extend(base64.b64decode(b64))

                        elif t in ("response.output_audio.done", "response.done"):
                            # 1) 파이썬 버퍼 비움
                            while len(buffer_audio) > 0:
                                await asyncio.sleep(0.01)

                            # 2) 하드웨어 재생 종료 대기
                            print("⏱️ HW playback 모니터링…")
                            checks = 0
                            while speaker_is_playing(speaker_card, speaker_dev):
                                await asyncio.sleep(0.05)
                                checks += 1
                                if checks > 200:  # 10s safety
                                    print("⚠️ HW wait timeout")
                                    break

                            # 3) 여유 120ms
                            await asyncio.sleep(0.12)

                            # 4) 마이크 재개
                            playing = False
                            prebuffered = False
                            playback_queue.clear()
                            mic_enabled = True
                            print("🔊 Mic enabled\n")

                        elif t == "input_audio_buffer.speech_started":
                            # 바지인: 재생 즉시 중단(드롭 + 재오픈 예약)
                            print("👂 Listening (barge-in)")
                            try:
                                speaker.close()
                            except Exception:
                                pass
                            speaker = open_speaker()
                            buffer_audio.clear()
                            prebuffered = False
                            playing = False
                            if not mic_enabled:
                                mic_enabled = True

                        elif t == "response.audio_transcript.delta":
                            print(msg.get("delta", ""), end="", flush=True)

                        elif t == "response.audio_transcript.done":
                            print()

                        elif t == "input_audio_buffer.speech_stopped":
                            print("🛑 Processing...")

                        elif t == "conversation.item.input_audio_transcription.completed":
                            print(f"👤 You: {msg.get('transcript','')}")

                        elif t == "error":
                            print(f"❌ Error: {msg.get('error',{}).get('message','Unknown')}")

                    except websockets.exceptions.ConnectionClosed:
                        if is_running:
                            print("❌ WebSocket closed")
                        break
                    except Exception as e:
                        if is_running:
                            print(f"⚠️ Receiver error: {e}")
                        break

            # 9) 태스크 실행
            feeder_t = asyncio.create_task(feeder())
            mic_t    = asyncio.create_task(mic_sender())
            recv_t   = asyncio.create_task(receiver())

            try:
                await asyncio.gather(feeder_t, mic_t, recv_t)
            finally:
                # 종료
                pass

    except KeyboardInterrupt:
        print("\n👋 종료합니다.")
    finally:
        try: mic.close()
        except: pass
        try: speaker.close()
        except: pass
        print("🧹 Cleanup complete")

if __name__ == "__main__":
    asyncio.run(main())