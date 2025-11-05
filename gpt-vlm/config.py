#!/usr/bin/env python3
"""
Configuration for GPT Vision + RealSense Integration
"""

# ============================================================
# OpenAI API Settings
# ============================================================
OPENAI_MODEL = "gpt-5-chat-latest"  # Options: "gpt-4o", "gpt-4o-mini", "gpt-5-chat-latest"
IMAGE_DETAIL = "low"  # Options: "low", "high", "auto"
MAX_TOKENS = 300  # Maximum tokens in response
TEMPERATURE = 0.7  # 0.0-2.0, higher = more creative

# ============================================================
# RealSense Camera Settings
# ============================================================
REALSENSE_WIDTH = 640
REALSENSE_HEIGHT = 480
REALSENSE_FPS = 30

# ============================================================
# Image Processing
# ============================================================
JPEG_QUALITY = 75  # 0-100, higher = better quality but more tokens
ANALYSIS_FPS = 1  # How often to send frames to GPT (1-2 recommended)
SEND_DEPTH_IMAGE = True  # Send depth image along with RGB (doubles token cost)

# ============================================================
# Logging Settings
# ============================================================
LOG_DIR = "/home/unitree/AIM-Robotics/gpt-vlm/logs"
SAVE_IMAGES = True  # Save analyzed images to disk
SAVE_RESPONSES = True  # Save GPT responses to JSON
LOG_CONSOLE = True  # Print responses to console

# ============================================================
# Performance Settings
# ============================================================
WARMUP_FRAMES = 30  # RealSense warm-up frames before analysis
ENABLE_TOKEN_TRACKING = True  # Track and display token usage costs
