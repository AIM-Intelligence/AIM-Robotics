#!/usr/bin/env python3
"""
G1 Realtime Multimodal with Autonomous Arm Control
- Voice + Vision + Arm Control
- USB mic/speaker (24kHz S16_LE mono)
- Realtime API server VAD + Function Calling
- AI autonomously decides when to use arm gestures based on conversation and vision

Tested with:
- Mic: ABKO N550
- Speaker: Fenda V720
- Camera: RealSense D435(i)
- Robot: Unitree G1
"""

import os, asyncio, json, base64, time, subprocess, re, glob, sys
import websockets
import queue
import cv2
import numpy as np
from concurrent.futures import ThreadPoolExecutor

# ---- Unitree SDK ----
sys.path.insert(0, '/home/unitree/unitree_sdk2_python')
from unitree_sdk2py.core.channel import ChannelFactoryInitialize
from unitree_sdk2py.g1.arm.g1_arm_action_client import G1ArmActionClient

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

import config
import prompts

# ================== Config from config.py ==================
OPENAI_API_KEY = config.OPENAI_API_KEY
MODEL  = config.OPENAI_MODEL
VOICE  = config.OPENAI_VOICE

AUDIO_RATE     = config.AUDIO_RATE
AUDIO_CHANNELS = config.AUDIO_CHANNELS
S16LE_BYTES    = config.S16LE_BYTES
MIC_CHUNK_FRAMES     = config.MIC_CHUNK_FRAMES
SPEAKER_CHUNK_FRAMES = config.SPEAKER_CHUNK_FRAMES
PREBUFFER_MS         = config.PREBUFFER_MS
PREBUFFER_BYTES      = int(AUDIO_RATE * S16LE_BYTES * PREBUFFER_MS / 1000)

# Vision
SEND_IMAGES = config.SEND_IMAGES
IMAGE_INTERVAL_SEC = config.IMAGE_SEND_INTERVAL
JPEG_QUALITY = config.JPEG_QUALITY
RS_WIDTH, RS_HEIGHT, RS_FPS = config.REALSENSE_WIDTH, config.REALSENSE_HEIGHT, config.REALSENSE_FPS
WARMUP_FRAMES = config.WARMUP_FRAMES

MIC_NAME_PATTERNS     = config.MIC_NAME_PATTERNS
SPEAKER_NAME_PATTERNS = config.SPEAKER_NAME_PATTERNS

# System prompt (override for autonomous arm control)
SYSTEM_PROMPT = prompts.get_prompt("G1_AUTONOMOUS_ARM")  # 자율 팔 제어용

# ================== Arm Control ==================
ARM_ACTIONS = {
    "wave": 26,
    "high wave": 26,
    "high five": 18,
    "heart": 20,
    "right heart": 21,
    "clap": 17,
    "hug": 19,
    "hands up": 15,
    "shake": 27,
    "shake hand": 27,
    "face wave": 25,
    "reject": 22,
    "no": 22,
    "kiss": 11,
    "two-hand kiss": 11,
    "left kiss": 12,
    "right kiss": 13,
    "x-ray": 24,
    "xray": 24,
    "release": 99,
}

# Global arm client (initialized in main)
g1_arm_client = None

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

def control_g1_arm_sync(gesture: str, action_id: int):
    """Synchronous arm control (runs in background thread)"""
    global g1_arm_client

    try:
        result = g1_arm_client.ExecuteAction(action_id)

        if result == 0:
            print(f"✅ Arm gesture '{gesture}' executed")

            # Auto release after action (like gpt-vlm)
            if action_id != 99:  # Don't release after release command
                time.sleep(0.5)  # Wait for gesture to complete
                print("🔓 Auto releasing arm...")
                release_result = g1_arm_client.ExecuteAction(99)

                if release_result == 0:
                    print("✅ Arm released")
                else:
                    print(f"⚠️  Release failed: {release_result}")
        else:
            print(f"❌ Arm control failed: {result}")
    except Exception as e:
        print(f"❌ Arm control exception: {e}")

def control_g1_arm(gesture: str) -> dict:
    """Execute G1 arm gesture (non-blocking)"""
    global g1_arm_client

    gesture_lower = gesture.lower()
    if gesture_lower not in ARM_ACTIONS:
        return {
            "success": False,
            "error": f"Unknown gesture: {gesture}. Available: {list(ARM_ACTIONS.keys())}"
        }

    if g1_arm_client is None:
        return {
            "success": False,
            "error": "Arm client not initialized"
        }

    action_id = ARM_ACTIONS[gesture_lower]
    print(f"\n🦾 Starting arm gesture: {gesture} (ID: {action_id})")

    # Execute in background thread (non-blocking)
    import threading
    thread = threading.Thread(target=control_g1_arm_sync, args=(gesture, action_id), daemon=True)
    thread.start()

    # Return immediately so AI can speak
    return {
        "success": True,
        "gesture": gesture,
        "message": f"Performing {gesture}"
    }

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
    global g1_arm_client

    assert OPENAI_API_KEY, "❌ Set OPENAI_API_KEY in .env"

    # Initialize G1 Arm Client
    print("🦾 Initializing G1 Arm Client...")
    try:
        ChannelFactoryInitialize(0, 'eth0')
        g1_arm_client = G1ArmActionClient()
        g1_arm_client.SetTimeout(10.0)
        g1_arm_client.Init()
        print("✅ G1 Arm Client ready")
    except Exception as e:
        print(f"⚠️  Arm client init failed: {e}")
        print("   Continuing without arm control...")
        g1_arm_client = None

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

            # Session: server VAD (auto commit), audio in/out, voice, system prompt, function calling
            await ws.send(json.dumps({
                "type": "session.update",
                "session": {
                    "modalities": ["audio", "text"],
                    "instructions": SYSTEM_PROMPT,  # ← System prompt from prompts.py
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
                    },
                    "tools": [
                        {
                            "type": "function",
                            "name": "control_g1_arm",
                            "description": "IMPORTANT: This function makes the robot perform a gesture. After calling this function, you MUST also provide a voice response. Do NOT just call the function and stay silent. Always combine gesture with speech. Example: User says 'hello' → call control_g1_arm('wave') AND say 'Hello! Nice to meet you!'",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "gesture": {
                                        "type": "string",
                                        "enum": list(ARM_ACTIONS.keys()),
                                        "description": "The gesture to perform (wave, clap, heart, high five, etc)"
                                    }
                                },
                                "required": ["gesture"]
                            }
                        }
                    ],
                    "tool_choice": "auto"
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

                # Track audio in current response
                response_has_audio = False
                response_has_function_call = False
                response_completed = False  # Track if we already handled response.done

                while is_running:
                    try:
                        msg = json.loads(await ws.recv())
                        t = msg.get("type")

                        if t == "response.created":
                            # New response → ensure speaker is clean, mute mic
                            buffer_audio.clear()
                            prebuffered = False
                            playing = False
                            response_has_audio = False
                            response_has_function_call = False
                            response_completed = False
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
                                response_has_audio = True  # Mark that we received audio

                        elif t == "response.done":
                            # Only handle once per response
                            if response_completed:
                                continue
                            response_completed = True

                            # Check if this response had audio
                            if not response_has_audio and response_has_function_call:
                                # Function-only response with no audio → don't unmute mic yet
                                # The AI will generate speech in the next response
                                print("🔧 Function-only response, waiting for speech...")
                                # Reset flags for next response
                                response_has_audio = False
                                response_has_function_call = False
                                continue

                            # Normal response with audio - proceed with playback wait
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
                            response_has_audio = False
                            response_has_function_call = False
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

                        elif t == "response.function_call_arguments.done":
                            # Function call completed
                            call_id = msg.get("call_id")
                            func_name = msg.get("name")
                            args_str = msg.get("arguments", "{}")

                            print(f"\n🔧 Function call: {func_name}")
                            response_has_function_call = True  # Mark that function was called

                            try:
                                args = json.loads(args_str)
                            except:
                                args = {}

                            # Execute function
                            if func_name == "control_g1_arm":
                                gesture = args.get("gesture", "")
                                result = control_g1_arm(gesture)  # Non-blocking call with auto-release

                                # Send result back to API
                                await ws.send(json.dumps({
                                    "type": "conversation.item.create",
                                    "item": {
                                        "type": "function_call_output",
                                        "call_id": call_id,
                                        "output": json.dumps(result)
                                    }
                                }))

                                # Trigger follow-up response for speech
                                await ws.send(json.dumps({
                                    "type": "response.create"
                                }))

                            else:
                                print(f"⚠️  Unknown function: {func_name}")

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