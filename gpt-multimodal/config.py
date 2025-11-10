#!/usr/bin/env python3
"""
Configuration for G1 Realtime Multimodal System
Audio + Vision integration with OpenAI Realtime API
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# OpenAI API Configuration
# ============================================================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_REALTIME_MODEL", "gpt-realtime")
OPENAI_VOICE = os.getenv("OPENAI_REALTIME_VOICE", "cedar")

# ============================================================
# RealSense Camera Configuration
# ============================================================
REALSENSE_WIDTH = 640
REALSENSE_HEIGHT = 480
REALSENSE_FPS = 30
WARMUP_FRAMES = 30  # Number of frames to skip during camera warmup

# ============================================================
# Image Sending Configuration
# ============================================================
IMAGE_SEND_INTERVAL = 5.0  # Send image every N seconds
JPEG_QUALITY = 75  # JPEG compression quality (0-100)
SEND_IMAGES = True  # Set to False to disable vision temporarily

# ============================================================
# Audio Configuration
# ============================================================
AUDIO_RATE = 24000  # OpenAI Realtime API uses 24kHz
AUDIO_CHANNELS = 1
S16LE_BYTES = 2

# Audio chunk sizes
MIC_CHUNK_FRAMES = 2400  # 100ms @ 24kHz
SPEAKER_CHUNK_FRAMES = 1200  # 50ms @ 24kHz
PREBUFFER_MS = 250  # Prebuffer for smooth playback

# USB audio device patterns
MIC_NAME_PATTERNS = ["N550", "ABKO", "USB", "Headset", "Microphone"]
SPEAKER_NAME_PATTERNS = ["V720", "Fenda", "USB", "Speaker", "Headphones"]

# ============================================================
# System Prompt
# ============================================================
# For g1_realtime_multimodal_tool.py (with autonomous arm control):
# SYSTEM_PROMPT_NAME = "G1_AUTONOMOUS_ARM_KR"  # 자율 팔 제어 (한국어)
# SYSTEM_PROMPT_NAME = "G1_AUTONOMOUS_ARM"     # Autonomous arm control (English)

# For g1_realtime_multimodal.py (vision only):
SYSTEM_PROMPT_NAME = "G1_AUTONOMOUS_ARM_KR"  # Change to desired prompt from prompts.py

# ============================================================
# Cost Tracking
# ============================================================
# Approximate costs (as of 2025):
# - Audio input: $60/hour
# - Audio output: $60/hour
# - Images (360/hour @ 10sec): ~$1.25/hour
# Total: ~$121.25/hour
