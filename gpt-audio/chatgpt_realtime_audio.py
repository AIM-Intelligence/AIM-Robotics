#!/usr/bin/env python3
"""
ChatGPT Realtime Audio for Unitree G1
Live voice conversations with ChatGPT using OpenAI's Realtime API and Unitree G1's speaker.
"""

import asyncio
import websockets
import json
import pyaudio
import base64
import os
from collections import deque
import numpy as np
import sys
import io
import wave
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Unitree SDK imports
SDK_PATH = "/home/unitree/unitree_sdk2_python"
EXAMPLE_AUDIO_PATH = os.path.join(SDK_PATH, "example", "g1", "audio")

for path in (SDK_PATH, EXAMPLE_AUDIO_PATH):
    if path not in sys.path:
        sys.path.insert(0, path)

from unitree_sdk2py.core.channel import ChannelFactoryInitialize
from unitree_sdk2py.g1.audio.g1_audio_client import AudioClient

# ============================================================
# CONFIGURATION
# ============================================================

training = """
[Your training prompt here - keeping it short for readability]
"""

SYSTEM_PROMPT = f"""{training}"""
VOICE = "verse"
TEMPERATURE = 0.8
MAX_TOKENS = 4096
CONVERSATION_HISTORY = [
    {"role": "user", "content": training},
]

# Audio settings
OPENAI_SAMPLE_RATE = 24000  # OpenAI uses 24kHz
G1_SAMPLE_RATE = 16000      # Unitree G1 uses 16kHz
USB_HEADSET_SAMPLE_RATE = 44100  # USB headset native sample rate
INPUT_SAMPLE_RATE = USB_HEADSET_SAMPLE_RATE  # Capture at native rate
CHUNK_SIZE = 2048  # Larger chunk for 44.1kHz
CHANNELS = 1

# Unitree G1 settings
G1_INTERFACE = "eth0"  # Network interface connected to G1
G1_STREAM_NAME = "openai_audio"
G1_CHUNK_BYTES = 32000  # Bytes to send per chunk to G1
G1_VOLUME = 100  # 0-100

# USB Headset settings (auto-detected as ABKO N550)
USB_HEADSET_DEVICE_INDEX = None  # Will be auto-detected

# ============================================================
# Audio Resampling Helper
# ============================================================

def resample_audio(audio_data, from_rate, to_rate):
    """Resample audio from one sample rate to another using numpy"""
    # Convert bytes to numpy array
    audio_array = np.frombuffer(audio_data, dtype=np.int16)
    
    # Calculate the new length
    duration = len(audio_array) / from_rate
    new_length = int(duration * to_rate)
    
    # Resample using numpy interpolation
    resampled = np.interp(
        np.linspace(0, len(audio_array), new_length),
        np.arange(len(audio_array)),
        audio_array
    ).astype(np.int16)
    
    return resampled.tobytes()

# ============================================================
# Main Class
# ============================================================

class RealtimeAudioChatG1:
    def __init__(self, api_key):
        self.api_key = api_key
        self.websocket = None
        self.audio = pyaudio.PyAudio()
        self.input_stream = None
        self.audio_queue = deque()
        self.is_running = False
        
        # Unitree G1 AudioClient
        self.g1_client = None
        self.g1_audio_buffer = bytearray()
        
    def init_g1_audio(self):
        """Initialize Unitree G1 audio client"""
        print(f"🤖 Initializing Unitree G1 audio on interface: {G1_INTERFACE}")
        try:
            ChannelFactoryInitialize(0, G1_INTERFACE)
            self.g1_client = AudioClient()
            self.g1_client.SetTimeout(10.0)
            self.g1_client.Init()
            
            # Set volume
            self.g1_client.SetVolume(G1_VOLUME)
            print(f"✅ G1 audio initialized (Volume: {G1_VOLUME}%)")
            return True
        except Exception as e:
            print(f"❌ Failed to initialize G1 audio: {e}")
            return False
    
    def find_usb_headset(self):
        """Auto-detect USB headset device index"""
        print("🔍 Searching for USB headset...")
        for i in range(self.audio.get_device_count()):
            info = self.audio.get_device_info_by_index(i)
            name = info.get('name', '').lower()
            if info['maxInputChannels'] > 0:
                # Look for USB audio devices
                if 'usb' in name or 'n550' in name or 'abko' in name:
                    print(f"✅ Found USB headset: [{i}] {info['name']}")
                    return i
        
        print("⚠️  USB headset not found, using default input")
        return None
            
    async def connect(self):
        """Connect to OpenAI Realtime API"""
        url = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "OpenAI-Beta": "realtime=v1"
        }
        
        print("🔌 Connecting to OpenAI Realtime API...")
        # Try both parameter names for compatibility with different websockets versions
        try:
            self.websocket = await websockets.connect(url, additional_headers=headers)
        except TypeError:
            # Fallback for older versions that use 'extra_headers'
            self.websocket = await websockets.connect(url, extra_headers=headers)
        print("✅ Connected!")
        
    async def configure_session(self):
        """Configure the session with system prompt and settings"""
        config = {
            "type": "session.update",
            "session": {
                "modalities": ["text", "audio"],
                "instructions": SYSTEM_PROMPT,
                "voice": VOICE,
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "input_audio_transcription": {
                    "model": "whisper-1"
                },
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 500
                },
                "temperature": TEMPERATURE,
                "max_response_output_tokens": MAX_TOKENS
            }
        }
        await self.websocket.send(json.dumps(config))
        print("⚙️  Session configured")
        
        # Load conversation history
        if CONVERSATION_HISTORY:
            await self.load_conversation_history()
    
    async def load_conversation_history(self):
        """Load conversation history into the session"""
        print(f"📚 Loading {len(CONVERSATION_HISTORY)} conversation turns...")
        
        for turn in CONVERSATION_HISTORY:
            role = turn.get("role")
            content = turn.get("content")
            
            if role == "user":
                message = {
                    "type": "conversation.item.create",
                    "item": {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": content}]
                    }
                }
                await self.websocket.send(json.dumps(message))
                
            elif role == "assistant":
                message = {
                    "type": "conversation.item.create",
                    "item": {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "text", "text": content}]
                    }
                }
                await self.websocket.send(json.dumps(message))
        
        print("✅ Conversation history loaded")
        
    def start_audio_input(self):
        """Initialize audio input stream from USB headset"""
        # Find USB headset
        usb_device_index = self.find_usb_headset()
        
        input_kwargs = {
            'format': pyaudio.paInt16,
            'channels': CHANNELS,
            'rate': INPUT_SAMPLE_RATE,
            'input': True,
            'frames_per_buffer': CHUNK_SIZE
        }
        
        if usb_device_index is not None:
            input_kwargs['input_device_index'] = usb_device_index
        
        self.input_stream = self.audio.open(**input_kwargs)
        print(f"🎤 Audio input started (USB Headset @ {INPUT_SAMPLE_RATE}Hz)")
        
    async def send_audio(self):
        """Capture audio from USB headset and send to OpenAI API"""
        while self.is_running:
            try:
                # Capture audio at USB headset's native rate (44.1kHz)
                audio_data = self.input_stream.read(CHUNK_SIZE, exception_on_overflow=False)
                
                # Resample from 44.1kHz to 24kHz for OpenAI
                audio_data_24k = resample_audio(audio_data, INPUT_SAMPLE_RATE, OPENAI_SAMPLE_RATE)
                
                audio_b64 = base64.b64encode(audio_data_24k).decode('utf-8')
                
                message = {
                    "type": "input_audio_buffer.append",
                    "audio": audio_b64
                }
                await self.websocket.send(json.dumps(message))
                await asyncio.sleep(0.01)
            except Exception as e:
                if self.is_running:
                    print(f"Error sending audio: {e}")
                break
                
    async def receive_messages(self):
        """Receive and process messages from the API"""
        while self.is_running:
            try:
                message = await self.websocket.recv()
                data = json.loads(message)
                await self.handle_message(data)
            except websockets.exceptions.ConnectionClosed:
                if self.is_running:
                    print("Connection closed")
                break
            except Exception as e:
                if self.is_running:
                    print(f"Error receiving message: {e}")
                break
                
    async def handle_message(self, data):
        """Handle different message types from the API"""
        msg_type = data.get("type")
        
        if msg_type == "response.audio.delta":
            # Receive audio response chunks (24kHz from OpenAI)
            audio_b64 = data.get("delta", "")
            if audio_b64:
                audio_data_24k = base64.b64decode(audio_b64)
                # Resample from 24kHz to 16kHz for G1
                audio_data_16k = resample_audio(audio_data_24k, OPENAI_SAMPLE_RATE, G1_SAMPLE_RATE)
                self.audio_queue.append(audio_data_16k)
                
        elif msg_type == "response.audio_transcript.delta":
            transcript = data.get("delta", "")
            if transcript:
                print(f"{transcript}", end="", flush=True)
                
        elif msg_type == "response.audio_transcript.done":
            print()
            
        elif msg_type == "input_audio_buffer.speech_started":
            print("👂 Listening...")
            
        elif msg_type == "input_audio_buffer.speech_stopped":
            print("🛑 Processing...")
            
        elif msg_type == "conversation.item.input_audio_transcription.completed":
            transcript = data.get("transcript", "")
            print(f"👤 You: {transcript}")
        
        elif msg_type == "session.updated":
            print("✅ Session configuration acknowledged")
            
        elif msg_type == "conversation.item.created":
            item_role = data.get("item", {}).get("role", "unknown")
            print(f"✅ History item acknowledged: {item_role}")
            
        elif msg_type == "error":
            print(f"❌ Error: {data.get('error', {}).get('message', 'Unknown error')}")
                
    async def play_audio_g1(self):
        """Send audio to Unitree G1 speaker"""
        while self.is_running:
            if self.audio_queue:
                try:
                    # Get audio chunk
                    audio_data = self.audio_queue.popleft()
                    self.g1_audio_buffer.extend(audio_data)
                    
                    # When buffer reaches threshold, send to G1
                    if len(self.g1_audio_buffer) >= G1_CHUNK_BYTES:
                        chunk_to_send = bytes(self.g1_audio_buffer[:G1_CHUNK_BYTES])
                        self.g1_audio_buffer = self.g1_audio_buffer[G1_CHUNK_BYTES:]
                        
                        # Send to G1 using PlayStream
                        await asyncio.get_event_loop().run_in_executor(
                            None,
                            self.g1_client.PlayStream,
                            G1_STREAM_NAME,
                            list(chunk_to_send)
                        )
                        
                except Exception as e:
                    if self.is_running:
                        print(f"\n⚠️  Audio playback error: {e}")
            else:
                await asyncio.sleep(0.01)
        
        # Flush remaining buffer
        if len(self.g1_audio_buffer) > 0:
            try:
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    self.g1_client.PlayStream,
                    G1_STREAM_NAME,
                    list(bytes(self.g1_audio_buffer))
                )
                self.g1_client.PlayStop(G1_STREAM_NAME)
            except:
                pass
                
    async def run(self):
        """Main run loop"""
        # Initialize G1 audio first
        if not self.init_g1_audio():
            print("❌ Failed to initialize G1 audio. Exiting...")
            return
        
        try:
            # Connect to OpenAI
            await self.connect()
            
            self.is_running = True
            
            # Start receiver task first
            receiver_task = asyncio.create_task(self.receive_messages())
            
            # Configure session
            await self.configure_session()
            
            # Start audio input
            self.start_audio_input()
            
            print("\n" + "="*60)
            print("🎙️  REALTIME AUDIO CHAT WITH CHATGPT ON UNITREE G1")
            print("="*60)
            print("\n💡 Tips:")
            print("   - Speak into your USB headset microphone")
            print("   - The AI will respond through G1's speaker")
            print("   - Press Ctrl+C to exit\n")
            print("="*60 + "\n")
            
            # Run all tasks
            await asyncio.gather(
                receiver_task,
                self.send_audio(),
                self.play_audio_g1()
            )
            
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
        except Exception as e:
            print(f"❌ Runtime Error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await self.cleanup()
            
    async def cleanup(self):
        """Clean up resources"""
        self.is_running = False
        
        await asyncio.sleep(0.1)
        
        if self.input_stream:
            self.input_stream.stop_stream()
            self.input_stream.close()
            
        self.audio.terminate()
        
        # Stop G1 audio
        if self.g1_client:
            try:
                self.g1_client.PlayStop(G1_STREAM_NAME)
            except:
                pass
        
        if self.websocket and self.websocket.open:
            await self.websocket.close()
            
        print("🧹 Cleaned up resources")


async def main():
    """Entry point"""
    api_key = os.getenv("OPENAI_API_KEY")
    
    if not api_key:
        print("❌ Error: OPENAI_API_KEY not found")
        print("\n💡 Set it using one of:")
        print("   1. Create .env file with: OPENAI_API_KEY=your-api-key-here")
        print("   2. Or export: export OPENAI_API_KEY='your-api-key-here'")
        return
    
    chat = RealtimeAudioChatG1(api_key)
    
    try:
        await chat.run()
    except Exception as e:
        print(f"❌ Main Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 Exiting...")