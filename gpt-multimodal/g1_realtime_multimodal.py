#!/usr/bin/env python3
"""
G1 Realtime Multimodal (Voice + Vision)
- USB mic/speaker (24kHz S16_LE mono)
- Realtime API server VAD (no manual commit)
- Hardware playback wait via /proc/asound before re-enabling mic
- Periodically inject latest RealSense frame as conversation item (no auto response)

Tested with:
- Mic: ABKO N550
- Speaker: Fenda V720
- Camera: RealSense D435(i)
"""

import os, asyncio, json, base64, time, subprocess, re, glob
import websockets
import queue
import cv2
import numpy as np
from concurrent.futures import ThreadPoolExecutor

# ---- Optional: RealSense ----
try:
    import pyrealsense2 as rs
    HAS_RS = True
except Exception:
    HAS_RS = False

# ---- ALSA ----
try:
    import alsaaudio
except ImportError:
    print("❌ pyalsaaudio not installed. `pip install pyalsaaudio`")
    raise

from dotenv import load_dotenv
load_dotenv()

# ================== Config ==================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MODEL  = os.getenv("OPENAI_REALTIME_MODEL", "gpt-realtime")
VOICE  = os.getenv("OPENAI_REALTIME_VOICE", "cedar")

AUDIO_RATE     = 24000
AUDIO_CHANNELS = 1
S16LE_BYTES    = 2
MIC_CHUNK_FRAMES     = 2400  # 100ms @24k
SPEAKER_CHUNK_FRAMES = 1200  # 50ms @24k
PREBUFFER_MS         = 250
PREBUFFER_BYTES      = int(AUDIO_RATE * S16LE_BYTES * PREBUFFER_MS / 1000)

# Vision
SEND_IMAGES = True
IMAGE_INTERVAL_SEC = 8.0
JPEG_QUALITY = 75
RS_WIDTH, RS_HEIGHT, RS_FPS = 640, 480, 30
WARMUP_FRAMES = 30

MIC_NAME_PATTERNS     = ["N550", "ABKO", "USB", "Headset", "Microphone"]
SPEAKER_NAME_PATTERNS = ["V720", "Fenda", "USB", "Speaker", "Headphones"]

# ================== Helpers ==================
def find_usb_audio_device(patterns, device_type="input"):
    cmd = 'arecord' if device_type == "input" else 'aplay'
    try:
        out = subprocess.check_output([cmd, '-l'], universal_newlines=True)
    except Exception as e:
        print(f"❌ {cmd} -l failed: {e}")
        return None, None, None

    for line in out.splitlines():
        # card 3: V720 [Fenda V720], device 0: USB Audio [USB Audio]
        m = re.search(r'card (\d+):\s+(\S+)\s+\[([^\]]+)\].*device (\d+)', line)
        if not m:
            continue
        card_num, card_id, card_name, dev_num = m.group(1), m.group(2), m.group(3), m.group(4)
        for p in patterns:
            if p in card_name or p in card_id:
                dev = f"plughw:CARD={card_id},DEV={dev_num}"
                print(f"✅ Found {device_type}: {card_name} -> {dev}")
                return dev, card_num, dev_num
    return None, None, None

def list_status_paths(card_num: str, dev_num: str):
    base = f"/proc/asound/card{card_num}/pcm{dev_num}p"
    return sorted(glob.glob(f"{base}/sub*/status"))

def speaker_is_playing(card_num: str, dev_num: str) -> bool:
    for path in list_status_paths(card_num, dev_num):
        try:
            with open(path, "r") as f:
                s = f.read()
                if "state: RUNNING" in s or "state: DRAINING" in s:
                    return True
        except Exception:
            pass
    return False

def encode_bgr_to_data_url(bgr: np.ndarray) -> str:
    ok, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    if not ok:
        return None
    b64 = base64.b64encode(buf.tobytes()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"

# ================== RealSense ==================
def init_realsense():
    if not HAS_RS:
        print("⚠️ pyrealsense2 not available, vision disabled")
        return None
    print("🎥 Initializing RealSense…")
    try:
        pipe = rs.pipeline()
        cfg = rs.config()
        cfg.enable_stream(rs.stream.color, RS_WIDTH, RS_HEIGHT, rs.format.bgr8, RS_FPS)
        pipe.start(cfg)
        # Warmup
        for _ in range(WARMUP_FRAMES):
            pipe.wait_for_frames()
        print("✅ RealSense ready")
        return pipe
    except Exception as e:
        print(f"❌ RealSense init failed: {e}")
        return None

# ================== Main ==================
async def main():
    assert OPENAI_API_KEY, "❌ Set OPENAI_API_KEY in .env"

    mic_device, mic_card, mic_dev = find_usb_audio_device(MIC_NAME_PATTERNS, "input")
    spk_device, spk_card, spk_dev = find_usb_audio_device(SPEAKER_NAME_PATTERNS, "output")
    if not mic_device or not spk_device:
        print("💡 Connect USB mic & speaker")
        return

    # Mic open
    print("🎤 Opening mic…")
    mic = alsaaudio.PCM(
        alsaaudio.PCM_CAPTURE,
        alsaaudio.PCM_NORMAL,
        device=mic_device,
        channels=AUDIO_CHANNELS,
        rate=AUDIO_RATE,
        format=alsaaudio.PCM_FORMAT_S16_LE,
        periodsize=MIC_CHUNK_FRAMES,
    )
    print("✅ Mic ready")

    # Speaker open (non-blocking)
    print("🔊 Opening speaker…")
    def open_speaker():
        return alsaaudio.PCM(
            alsaaudio.PCM_PLAYBACK,
            alsaaudio.PCM_NONBLOCK,
            device=spk_device,
            channels=AUDIO_CHANNELS,
            rate=AUDIO_RATE,
            format=alsaaudio.PCM_FORMAT_S16_LE,
            periodsize=SPEAKER_CHUNK_FRAMES,
        )
    speaker = open_speaker()
    print("✅ Speaker ready (non-blocking)")

    # RealSense
    rs_pipeline = init_realsense() if SEND_IMAGES else None

    # Connect Realtime
    url = f"wss://api.openai.com/v1/realtime?model={MODEL}"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "OpenAI-Beta": "realtime=v1",
    }
    print("🔌 Connecting Realtime…")

    try:
        async with websockets.connect(url, extra_headers=headers, ping_timeout=10, close_timeout=5) as ws:
            print("✅ Realtime connected")

            # Session: server VAD (auto commit), audio in/out, voice
            await ws.send(json.dumps({
                "type": "session.update",
                "session": {
                    "modalities": ["audio", "text"],
                    "voice": VOICE,
                    "input_audio_format": "pcm16",
                    "output_audio_format": "pcm16",
                    "input_audio_transcription": {"model": "whisper-1"},
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": 0.5,
                        "prefix_padding_ms": 300,
                        "silence_duration_ms": 500,
                        # create_response default true → let server auto-commit & respond
                    }
                }
            }))
            print("⚙️  Session configured")

            print("\n" + "="*60)
            print("🎙️  REALTIME 멀티모달(음성+시각) 시작")
            print("말하면 인식 → 응답은 스피커로 재생")
            print("📷 주기적으로 최신 프레임을 대화에 주입(응답 자동 생성 없음)")
            print("Ctrl+C 로 종료")
            print("="*60 + "\n")

            # -------- State --------
            buffer_audio = bytearray()
            mic_enabled  = True
            prebuffered  = False
            playing      = False
            is_running   = True
            retry_chunk  = None
            last_image_ts = 0.0
            latest_image = None

            # Mic thread → queue
            mic_q: "queue.Queue[bytes]" = queue.Queue(maxsize=200)
            executor = ThreadPoolExecutor(max_workers=2)

            def mic_reader():
                while is_running:
                    try:
                        nframes, data = mic.read()
                        if nframes > 0:
                            try:
                                mic_q.put(data, timeout=0.1)
                            except queue.Full:
                                pass
                    except Exception as e:
                        if is_running:
                            print(f"⚠️ Mic read error: {e}")
                        break

            executor.submit(mic_reader)

            # Camera capture thread (updates latest_image)
            def cam_reader():
                nonlocal latest_image
                if not rs_pipeline:
                    return
                while is_running:
                    try:
                        frames = rs_pipeline.wait_for_frames()
                        c = frames.get_color_frame()
                        if c:
                            latest_image = np.asanyarray(c.get_data())
                    except Exception:
                        time.sleep(0.05)

            if rs_pipeline:
                executor.submit(cam_reader)

            # -------- Tasks --------
            async def feeder():
                nonlocal playing, prebuffered, retry_chunk, speaker
                bytes_per_chunk = SPEAKER_CHUNK_FRAMES * S16LE_BYTES

                while is_running:
                    await asyncio.sleep(0)

                    if not prebuffered and not playing:
                        if len(buffer_audio) >= PREBUFFER_BYTES:
                            prebuffered = True
                            print("🔊 Prebuffer 완료 → 재생 시작")
                        else:
                            await asyncio.sleep(0.005)
                            continue

                    if retry_chunk is not None:
                        chunk = retry_chunk
                        retry_chunk = None
                    elif len(buffer_audio) >= bytes_per_chunk:
                        chunk = bytes(buffer_audio[:bytes_per_chunk])
                        del buffer_audio[:bytes_per_chunk]
                    else:
                        await asyncio.sleep(0.004)
                        continue

                    try:
                        written_frames = speaker.write(chunk)  # 0 => EAGAIN
                        if written_frames <= 0:
                            retry_chunk = chunk
                            await asyncio.sleep(0.01)
                            continue

                        written_bytes = written_frames * S16LE_BYTES
                        if written_bytes < len(chunk):
                            rest = chunk[written_bytes:]
                            buffer_audio[:0] = rest  # write the rest next
                            await asyncio.sleep(0.005)
                        else:
                            playing = True
                            await asyncio.sleep(0.045)  # a tad under 50ms
                    except alsaaudio.ALSAAudioError:
                        retry_chunk = chunk
                        await asyncio.sleep(0.01)
                    except Exception as e:
                        print(f"⚠️ Speaker error: {e}")
                        await asyncio.sleep(0.05)

            async def mic_sender():
                nonlocal mic_enabled
                while is_running:
                    try:
                        if mic_enabled:
                            try:
                                data = mic_q.get_nowait()
                                await ws.send(json.dumps({
                                    "type": "input_audio_buffer.append",
                                    "audio": base64.b64encode(data).decode("ascii"),
                                }))
                            except queue.Empty:
                                pass
                        else:
                            # drain mic queue while muted
                            try:
                                mic_q.get_nowait()
                            except queue.Empty:
                                pass
                        await asyncio.sleep(0.008)
                    except Exception as e:
                        if is_running:
                            print(f"⚠️ Mic send error: {e}")
                        break

            async def image_injector():
                nonlocal last_image_ts
                if not SEND_IMAGES or not rs_pipeline:
                    return
                while is_running:
                    now = time.time()
                    if (now - last_image_ts) >= IMAGE_INTERVAL_SEC and latest_image is not None:
                        data_url = encode_bgr_to_data_url(latest_image)
                        if data_url:
                            # IMPORTANT: input_image + image_url (data URL)
                            await ws.send(json.dumps({
                                "type": "conversation.item.create",
                                "item": {
                                    "type": "message",
                                    "role": "user",
                                    "content": [
                                        {
                                            "type": "input_image",
                                            "image_url": data_url
                                        },
                                        {
                                            "type": "input_text",
                                            "text": "(자동 주입된 최신 카메라 프레임)"
                                        }
                                    ]
                                }
                            }))
                            print("📷 이미지 프레임 주입 (응답 생성 안 함)")
                            last_image_ts = now
                    await asyncio.sleep(0.2)

            async def receiver():
                nonlocal mic_enabled, prebuffered, playing, speaker
                while is_running:
                    try:
                        msg = json.loads(await ws.recv())
                        t = msg.get("type")

                        if t == "response.created":
                            # New response → ensure speaker is clean, mute mic
                            buffer_audio.clear()
                            prebuffered = False
                            playing = False
                            try:
                                speaker.close()
                            except Exception:
                                pass
                            speaker = open_speaker()
                            print("🔁 Speaker reopen (new response)")
                            if mic_enabled:
                                mic_enabled = False
                                print("🔇 Mic muted (AI speaking)")

                        elif t in ("response.output_audio.delta", "response.audio.delta"):
                            # stream audio
                            b64 = msg.get("delta") or msg.get("audio") or ""
                            if b64:
                                buffer_audio.extend(base64.b64decode(b64))

                        elif t in ("response.output_audio.done", "response.done"):
                            # 1) drain python buffer
                            while len(buffer_audio) > 0:
                                await asyncio.sleep(0.01)

                            # 2) wait hardware playback
                            checks = 0
                            while speaker_is_playing(spk_card, spk_dev):
                                await asyncio.sleep(0.05)
                                checks += 1
                                if checks > 200:  # ~10s safety
                                    print("⚠️ HW wait timeout")
                                    break

                            # 3) small safety margin
                            await asyncio.sleep(0.12)

                            # 4) reopen mic
                            playing = False
                            prebuffered = False
                            mic_enabled = True
                            print("🔊 Mic enabled")

                        elif t == "input_audio_buffer.speech_started":
                            # barge-in: stop playback ASAP
                            print("👂 Listening(바지인)")
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

            # Run tasks
            feeder_t = asyncio.create_task(feeder())
            mic_t    = asyncio.create_task(mic_sender())
            img_t    = asyncio.create_task(image_injector())
            recv_t   = asyncio.create_task(receiver())

            try:
                await asyncio.gather(feeder_t, mic_t, img_t, recv_t)
            finally:
                pass

    except KeyboardInterrupt:
        print("\n👋 Bye")
    finally:
        try: mic.close()
        except: pass
        try: speaker.close()
        except: pass
        if rs_pipeline: 
            try: rs_pipeline.stop()
            except: pass
        print("🧹 Cleanup complete")

if __name__ == "__main__":
    asyncio.run(main())