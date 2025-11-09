#!/usr/bin/env python3
"""
Unitree G1 Realtime Audio Chat with OpenAI
Smooth speaker output + microphone input with precise playback tracking
"""

import os, asyncio, json, base64, time, subprocess, re
import websockets
import audioop
import queue
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
import prompts

# Unitree DDS
from unitree_sdk2py.core.channel import ChannelFactoryInitialize
from unitree_sdk2py.g1.audio.g1_audio_client import AudioClient

# ALSA microphone
try:
    import alsaaudio
except ImportError:
    print("❌ Error: pyalsaaudio not installed")
    print("   Install: pip install pyalsaaudio")
    exit(1)

load_dotenv()

# ============================================================
# Configuration
# ============================================================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MODEL = "gpt-realtime"
VOICE = "cedar"
APP_NAME = "realtime_chat"

# System prompt selection
# 옵션: "DEFAULT", "FRIENDLY", "EXPERT", "KOREAN_TUTOR", "CODING_MENTOR", "G1_ROBOT", "G1_ROBOT_KR"
SYSTEM_PROMPT_NAME = "G1_ROBOT"  # ← 원하는 프롬프트로 변경

# Microphone settings (24kHz for OpenAI)
MIC_RATE = 24000
MIC_CHANNELS = 1
MIC_CHUNK = 2400  # 100ms chunks for better efficiency
MIC_NAME_PATTERNS = ["N550", "ABKO", "USB"]

# ============================================================
# Load System Prompt
# ============================================================
def load_system_prompt():
    """Get system prompt from prompts.py"""
    prompt = prompts.get_prompt(SYSTEM_PROMPT_NAME)
    print(f"✅ System prompt: {SYSTEM_PROMPT_NAME}")
    return prompt

# Speaker settings (16kHz for G1)
CHUNK_MS = 50
BYTES_PER_SEC_16K = 16000 * 2
CHUNK_BYTES_16K = BYTES_PER_SEC_16K * CHUNK_MS // 1000
PREBUFFER_MS = 120

# ============================================================
# Resample 24k -> 16k
# ============================================================
class RateConverter24kTo16k:
    def __init__(self):
        self.state = None
    def push(self, pcm16_24k_bytes: bytes) -> bytes:
        out, self.state = audioop.ratecv(pcm16_24k_bytes, 2, 1, 24000, 16000, self.state)
        return out

# ============================================================
# Helper: Find microphone
# ============================================================
def find_microphone_device():
    """Find USB microphone by name pattern"""
    print("🔍 Searching for USB microphone...")
    try:
        output = subprocess.check_output(['arecord', '-l'], universal_newlines=True)

        for line in output.split('\n'):
            match = re.search(r'card (\d+):\s+(\S+)\s+\[([^\]]+)\].*device (\d+)', line)
            if match:
                card_id = match.group(2)
                card_name = match.group(3)
                device_num = match.group(4)

                for pattern in MIC_NAME_PATTERNS:
                    if pattern in card_name or pattern in card_id:
                        device_string = f"plughw:CARD={card_id},DEV={device_num}"
                        print(f"✅ Found: {card_name}")
                        print(f"   Device: {device_string}")
                        return device_string

        print("❌ No USB microphone found")
        return None
    except Exception as e:
        print(f"❌ Error finding microphone: {e}")
        return None

# ============================================================
# Helper: Network interface
# ============================================================
def autodetect_iface():
    try:
        import netifaces
        for iface in netifaces.interfaces():
            addrs = netifaces.ifaddresses(iface).get(netifaces.AF_INET, [])
            for a in addrs:
                ip = a.get('addr')
                if ip and ip.startswith("192.168.123."):
                    return iface
    except Exception:
        pass
    return None

# ============================================================
# Main
# ============================================================
async def main():
    assert OPENAI_API_KEY, "❌ OPENAI_API_KEY not set in .env"

    # Find microphone
    mic_device = find_microphone_device()
    if not mic_device:
        print("💡 Please connect USB microphone")
        return

    # Initialize DDS
    nic = os.getenv("UT_NET_IFACE") or autodetect_iface() or "eth0"
    print(f"[DDS] Initializing on {nic}")
    ChannelFactoryInitialize(0, nic)

    # G1 audio client
    ac = AudioClient()
    ac.Init()
    print("✅ G1 Audio Client initialized")

    # Initialize microphone
    print(f"🎤 Opening microphone...")
    try:
        mic = alsaaudio.PCM(
            alsaaudio.PCM_CAPTURE,
            alsaaudio.PCM_NORMAL,
            device=mic_device,
            channels=MIC_CHANNELS,
            rate=MIC_RATE,
            format=alsaaudio.PCM_FORMAT_S16_LE,
            periodsize=MIC_CHUNK
        )
        print("✅ Microphone ready")
    except Exception as e:
        print(f"❌ Microphone failed: {e}")
        return

    # Load system prompt
    system_prompt = load_system_prompt()

    # Connect to OpenAI Realtime
    url = f"wss://api.openai.com/v1/realtime?model={MODEL}"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "OpenAI-Beta": "realtime=v1"}
    print("🔌 Connecting to OpenAI...")

    try:
        async with websockets.connect(url, extra_headers=headers, ping_timeout=10, close_timeout=5) as ws:
            print("✅ Connected to OpenAI Realtime API")

            # Configure session (with system prompt)
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
            print("⚙️  Session configured")

            print("\n" + "="*60)
            print("🎙️  G1 REALTIME CHAT")
            print("="*60)
            print("💡 Speak into your USB microphone")
            print("   AI responds through G1 speaker")
            print("   Press Ctrl+C to exit")
            print("="*60 + "\n")

            # Audio buffers
            resampler = RateConverter24kTo16k()
            buffer16k = bytearray()
            stream_id = str(int(time.time()*1000))
            playing = False
            prebuffered = False
            mic_enabled = True
            is_running = True
            
            # ★ Playback queue: tracks (send_time, chunk_duration) for each chunk sent to G1
            playback_queue = deque()

            # Microphone queue for thread-safe operation
            mic_queue = queue.Queue(maxsize=100)
            executor = ThreadPoolExecutor(max_workers=1)

            # Microphone reader thread
            def mic_reader_thread():
                while is_running:
                    try:
                        length, data = mic.read()
                        if length > 0:
                            try:
                                mic_queue.put(data, timeout=0.1)
                            except queue.Full:
                                pass
                    except Exception as e:
                        if is_running:
                            print(f"\n⚠️  Mic read error: {e}")
                        break

            # Start microphone reader thread
            mic_future = executor.submit(mic_reader_thread)

            # Speaker feeder task - WITH PLAYBACK QUEUE TRACKING
            async def feeder():
                nonlocal playing, prebuffered
                PREBUFFER_BYTES = BYTES_PER_SEC_16K * PREBUFFER_MS // 1000

                while is_running:
                    await asyncio.sleep(0)

                    if not prebuffered and not playing:
                        if len(buffer16k) >= PREBUFFER_BYTES:
                            prebuffered = True
                            print("🔊 Prebuffer complete, starting playback...")
                        else:
                            await asyncio.sleep(0.005)
                            continue

                    if len(buffer16k) >= CHUNK_BYTES_16K:
                        chunk = bytes(buffer16k[:CHUNK_BYTES_16K])
                        del buffer16k[:CHUNK_BYTES_16K]
                        try:
                            ac.PlayStream(APP_NAME, stream_id, chunk)
                        except TypeError:
                            ac.PlayStream(APP_NAME, stream_id, list(chunk))
                        
                        # ★ Track playback: (send_time, chunk_duration)
                        send_time = time.time()
                        chunk_duration = CHUNK_MS / 1000.0  # 0.05 seconds
                        playback_queue.append((send_time, chunk_duration))
                        
                        playing = True
                        await asyncio.sleep(CHUNK_MS/1000.0 * 0.9)
                    else:
                        await asyncio.sleep(0.005)

            # Microphone sender task
            async def mic_sender():
                nonlocal mic_enabled
                while is_running:
                    try:
                        if mic_enabled:
                            try:
                                data = mic_queue.get_nowait()
                                audio_b64 = base64.b64encode(data).decode('utf-8')
                                await ws.send(json.dumps({
                                    "type": "input_audio_buffer.append",
                                    "audio": audio_b64
                                }))
                            except queue.Empty:
                                pass
                        else:
                            # Clear queue while muted
                            try:
                                mic_queue.get_nowait()
                            except queue.Empty:
                                pass

                        await asyncio.sleep(0.01)
                    except Exception as e:
                        if is_running:
                            print(f"\n⚠️  Mic send error: {e}")
                        break

            # Message receiver task - WITH QUEUE RESET ON NEW RESPONSE
            async def receiver():
                nonlocal playing, stream_id, prebuffered, mic_enabled
                while is_running:
                    try:
                        msg = json.loads(await ws.recv())
                        t = msg.get("type")

                        # ★ AI response started - RESET queue and mute microphone
                        if t == "response.created":
                            playback_queue.clear()  # ← Reset queue for new response!
                            if mic_enabled:
                                mic_enabled = False
                                print("🔇 Mic muted (AI speaking)")

                        # Audio delta
                        elif t in ("response.output_audio.delta", "response.audio.delta"):
                            if mic_enabled:
                                mic_enabled = False
                                print("🔇 Mic muted (AI speaking)")

                            b64 = msg.get("delta") or msg.get("audio") or ""
                            if b64:
                                pcm24k = base64.b64decode(b64)
                                pcm16k = resampler.push(pcm24k)
                                buffer16k.extend(pcm16k)

                        # # ★ Audio done - calculate wait time from queue
                        # elif t in ("response.output_audio.done", "response.done"):
                        #     # Drain Python buffer
                        #     while len(buffer16k) > 0:
                        #         await asyncio.sleep(0.01)
                            
                        #     # ★ Calculate wait time: queue size × chunk duration + safety margin
                        #     num_chunks = len(playback_queue)
                        #     total_wait = num_chunks * (CHUNK_MS / 1000.0)
                            
                        #     # Add safety margin for network/buffer delays
                        #     wait_time = total_wait + 0.2  # 200ms safety margin
                            
                        #     if num_chunks > 0:
                        #         print(f"⏱️  Waiting {wait_time:.2f}s (G1 buffer: {num_chunks} chunks)")
                        #         await asyncio.sleep(wait_time)
                        #     else:
                        #         print(f"⏱️  No wait needed (buffer empty)")
                        #         await asyncio.sleep(0.05)
                            
                        #     ac.PlayStop(APP_NAME)
                        #     playing = False
                        #     prebuffered = False
                        #     stream_id = str(int(time.time()*1000))
                        #     playback_queue.clear()  # Clear after done
                            
                        #     mic_enabled = True
                        #     print("🔊 Mic enabled")

                        elif t in ("response.output_audio.done", "response.done"):
                            # Drain Python buffer
                            while len(buffer16k) > 0:
                                await asyncio.sleep(0.01)
                            
                            # ★ 보수적 계산: 최근 청크들은 무조건 재생 중으로 간주
                            current_time = time.time()
                            
                            # G1 버퍼 크기 고려: 최근 10개 청크 (0.5초)는 무조건 재생 중
                            recent_chunks = list(playback_queue)[-10:] if len(playback_queue) >= 10 else list(playback_queue)
                            
                            # 각 청크의 남은 시간 계산
                            total_remaining_time = 0
                            for send_time, chunk_duration in recent_chunks:
                                elapsed = current_time - send_time
                                remaining = chunk_duration - elapsed
                                # 음수여도 G1 버퍼 고려해서 최소 시간 보장
                                if remaining < 0:
                                    remaining = 0.05  # 최소 50ms
                                total_remaining_time += remaining
                            
                            # 큰 여유 시간 추가
                            wait_time = total_remaining_time + 0.5  # 500ms 여유
                            
                            print(f"⏱️  Waiting {wait_time:.2f}s (safety: recent {len(recent_chunks)} chunks + buffer)")
                            await asyncio.sleep(wait_time)
                            
                            ac.PlayStop(APP_NAME)
                            playing = False
                            prebuffered = False
                            stream_id = str(int(time.time()*1000))
                            playback_queue.clear()
                            
                            mic_enabled = True
                            print("🔊 Mic enabled")
                            
                        # User speaking - stop playback
                        elif t == "input_audio_buffer.speech_started":
                            print("👂 Listening...")
                            ac.PlayStop(APP_NAME)
                            playing = False
                            buffer16k.clear()
                            playback_queue.clear()  # Clear queue on interruption
                            if not mic_enabled:
                                mic_enabled = True

                        # Transcript display
                        elif t == "response.audio_transcript.delta":
                            print(msg.get("delta", ""), end="", flush=True)

                        elif t == "response.audio_transcript.done":
                            print()

                        elif t == "input_audio_buffer.speech_stopped":
                            print("🛑 Processing...")

                        elif t == "conversation.item.input_audio_transcription.completed":
                            transcript = msg.get("transcript", "")
                            print(f"👤 You: {transcript}")

                        elif t == "error":
                            error_msg = msg.get('error', {}).get('message', 'Unknown')
                            print(f"❌ Error: {error_msg}")

                    except websockets.exceptions.ConnectionClosed:
                        if is_running:
                            print("\n❌ Connection closed")
                        break
                    except Exception as e:
                        if is_running:
                            print(f"\n⚠️  Receive error: {e}")
                        break

            # Start all tasks
            feeder_task = asyncio.create_task(feeder())
            mic_task = asyncio.create_task(mic_sender())
            recv_task = asyncio.create_task(receiver())

            try:
                await asyncio.gather(feeder_task, mic_task, recv_task)
            except KeyboardInterrupt:
                print("\n\n👋 Goodbye!")
            finally:
                is_running = False
                feeder_task.cancel()
                mic_task.cancel()
                recv_task.cancel()
                executor.shutdown(wait=False)
                await asyncio.sleep(0.1)

    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
    except Exception as e:
        print(f"\n❌ Connection error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        mic.close()
        ac.PlayStop(APP_NAME)
        print("🧹 Cleanup complete")

if __name__ == "__main__":
    asyncio.run(main())