#!/usr/bin/env python3
"""
GPT Vision + RealSense D435i Integration
Real-time scene analysis using OpenAI's GPT Vision API with Intel RealSense camera
"""

import asyncio
import pyrealsense2 as rs
import numpy as np
import cv2
import base64
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from openai import AsyncOpenAI
from dotenv import load_dotenv

import config
import prompts

# Load environment variables
load_dotenv()

# ============================================================
# GPT Vision Analyzer
# ============================================================

class GPTRealsenseAnalyzer:
    def __init__(self, api_key):
        self.api_key = api_key
        self.client = AsyncOpenAI(api_key=api_key)

        # RealSense pipeline
        self.pipeline = None
        self.pipeline_started = False

        # Analysis state
        self.is_running = False
        self.frame_count = 0
        self.analysis_count = 0

        # Token tracking
        self.total_input_tokens = 0
        self.total_output_tokens = 0

        # Timing
        self.start_time = None
        self.last_analysis_time = 0

        # Logging
        self.log_dir = Path(config.LOG_DIR)
        if config.SAVE_IMAGES or config.SAVE_RESPONSES:
            self.log_dir.mkdir(parents=True, exist_ok=True)

    def init_realsense(self):
        """Initialize RealSense D435i camera"""
        print("🎥 Initializing RealSense D435i...")

        try:
            self.pipeline = rs.pipeline()
            rs_config = rs.config()

            rs_config.enable_stream(
                rs.stream.depth,
                config.REALSENSE_WIDTH,
                config.REALSENSE_HEIGHT,
                rs.format.z16,
                config.REALSENSE_FPS
            )
            rs_config.enable_stream(
                rs.stream.color,
                config.REALSENSE_WIDTH,
                config.REALSENSE_HEIGHT,
                rs.format.bgr8,
                config.REALSENSE_FPS
            )

            print(f"  - Depth stream: {config.REALSENSE_WIDTH}x{config.REALSENSE_HEIGHT} @ {config.REALSENSE_FPS}fps")
            print(f"  - Color stream: {config.REALSENSE_WIDTH}x{config.REALSENSE_HEIGHT} @ {config.REALSENSE_FPS}fps")

            # Start pipeline (wait to prevent "Device busy" error)
            print("  - Waiting for device to be ready...")
            time.sleep(1.0)
            profile = self.pipeline.start(rs_config)
            self.pipeline_started = True
            time.sleep(0.3)

            # Camera intrinsics
            color_stream = profile.get_stream(rs.stream.color).as_video_stream_profile()
            intrinsics = color_stream.get_intrinsics()
            print(f"  ✓ Pipeline started")
            print(f"  - Focal length: fx={intrinsics.fx:.1f}, fy={intrinsics.fy:.1f}")

            # Warm-up
            print(f"  - Warming up camera ({config.WARMUP_FRAMES} frames)...")
            for i in range(config.WARMUP_FRAMES):
                self.pipeline.wait_for_frames()
            print("  ✓ Camera ready")

            return True

        except Exception as e:
            print(f"❌ RealSense initialization failed: {e}")
            if self.pipeline_started:
                self.pipeline.stop()
            return False

    def encode_image(self, bgr_image):
        """Encode BGR image to base64 JPEG"""
        _, buffer = cv2.imencode(
            '.jpg',
            bgr_image,
            [cv2.IMWRITE_JPEG_QUALITY, config.JPEG_QUALITY]
        )
        return base64.b64encode(buffer.tobytes()).decode('utf-8')

    def encode_depth_image(self, depth_image):
        """Encode depth image to base64 JPEG (colorized for visualization)"""
        # Normalize depth to 0-255 for visualization
        depth_normalized = cv2.normalize(depth_image, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)

        # Apply colormap for better visualization
        depth_colorized = cv2.applyColorMap(depth_normalized, cv2.COLORMAP_JET)

        # Encode to JPEG
        _, buffer = cv2.imencode(
            '.jpg',
            depth_colorized,
            [cv2.IMWRITE_JPEG_QUALITY, config.JPEG_QUALITY]
        )
        return base64.b64encode(buffer.tobytes()).decode('utf-8')

    def get_center_depth(self, depth_frame):
        """Get depth measurement at center of frame"""
        cx = config.REALSENSE_WIDTH // 2
        cy = config.REALSENSE_HEIGHT // 2

        depth_m = depth_frame.get_distance(cx, cy)
        return depth_m if depth_m > 0 else None

    async def analyze_frame(self, bgr_image, depth_image, depth_m, prompt_template=prompts.SCENE_UNDERSTANDING_KR):
        """Send frame to GPT Vision API for analysis"""

        # Build prompt with depth
        prompt_text = prompts.build_prompt(
            prompt_template,
            depth_m=depth_m,
            include_depth_image=config.SEND_DEPTH_IMAGE
        )

        # Encode RGB image
        base64_rgb = self.encode_image(bgr_image)

        # Build content list
        content = [
            {"type": "text", "text": prompt_text},
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{base64_rgb}",
                    "detail": config.IMAGE_DETAIL
                }
            }
        ]

        # Optionally add depth image
        if config.SEND_DEPTH_IMAGE and depth_image is not None:
            base64_depth = self.encode_depth_image(depth_image)
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{base64_depth}",
                    "detail": config.IMAGE_DETAIL
                }
            })

        try:
            # API call
            response = await self.client.chat.completions.create(
                model=config.OPENAI_MODEL,
                messages=[{
                    "role": "user",
                    "content": content
                }],
                max_tokens=config.MAX_TOKENS,
                temperature=config.TEMPERATURE
            )

            # Extract response
            analysis = response.choices[0].message.content

            # Track tokens
            if config.ENABLE_TOKEN_TRACKING and hasattr(response, 'usage'):
                self.total_input_tokens += response.usage.prompt_tokens
                self.total_output_tokens += response.usage.completion_tokens

            return {
                "success": True,
                "analysis": analysis,
                "prompt": prompt_text,
                "depth_m": depth_m,
                "tokens": {
                    "input": response.usage.prompt_tokens if hasattr(response, 'usage') else None,
                    "output": response.usage.completion_tokens if hasattr(response, 'usage') else None
                }
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "prompt": prompt_text,
                "depth_m": depth_m
            }

    def save_result(self, bgr_image, result, timestamp):
        """Save analysis result and image to disk"""

        # Save image
        if config.SAVE_IMAGES and bgr_image is not None:
            image_path = self.log_dir / f"frame_{timestamp}.jpg"
            cv2.imwrite(str(image_path), bgr_image)

        # Save response
        if config.SAVE_RESPONSES:
            result_path = self.log_dir / f"analysis_{timestamp}.json"
            with open(result_path, 'w') as f:
                json.dump({
                    "timestamp": timestamp,
                    "analysis_count": self.analysis_count,
                    **result
                }, f, indent=2)

    def print_analysis(self, result, analysis_time_ms):
        """Print analysis result to console"""
        if not config.LOG_CONSOLE:
            return

        print("\n" + "=" * 60)
        print(f"Analysis #{self.analysis_count} | {analysis_time_ms:.1f}ms")
        print("=" * 60)

        if result["success"]:
            print(f"\n📍 Depth: {result['depth_m']:.2f}m" if result['depth_m'] else "\n📍 Depth: N/A")
            print(f"\n🤖 GPT Analysis:\n")
            print(result["analysis"])

            if result["tokens"]["input"]:
                print(f"\n📊 Tokens: {result['tokens']['input']} in / {result['tokens']['output']} out")
        else:
            print(f"\n❌ Error: {result['error']}")

        print("=" * 60)

    async def run(self):
        """Main run loop"""

        # Initialize camera
        if not self.init_realsense():
            print("❌ Failed to initialize camera")
            return

        print("\n" + "=" * 60)
        print("🎥 GPT VISION + REALSENSE ANALYZER")
        print("=" * 60)
        print(f"\nConfiguration:")
        print(f"  Model:         {config.OPENAI_MODEL}")
        print(f"  Detail:        {config.IMAGE_DETAIL}")
        print(f"  JPEG Quality:  {config.JPEG_QUALITY}%")
        print(f"  Analysis Rate: {config.ANALYSIS_FPS} fps")
        print(f"  Resolution:    {config.REALSENSE_WIDTH}x{config.REALSENSE_HEIGHT}")
        print(f"  Depth Image:   {'Enabled (2x tokens)' if config.SEND_DEPTH_IMAGE else 'Disabled'}")
        print("\n" + "=" * 60)
        print("Press Ctrl+C to stop")
        print("=" * 60)

        self.is_running = True
        self.start_time = time.time()

        try:
            while self.is_running:
                # Get frames
                frames = self.pipeline.wait_for_frames()
                depth_frame = frames.get_depth_frame()
                color_frame = frames.get_color_frame()

                if not depth_frame or not color_frame:
                    continue

                self.frame_count += 1

                # Continuous analysis without delay
                # Convert to numpy arrays
                depth_image = np.asanyarray(depth_frame.get_data())
                color_image = np.asanyarray(color_frame.get_data())

                # Get center depth
                depth_m = self.get_center_depth(depth_frame)

                # Analyze frame
                analysis_start = time.time()
                result = await self.analyze_frame(color_image, depth_image, depth_m)
                analysis_end = time.time()
                analysis_time_ms = (analysis_end - analysis_start) * 1000

                self.analysis_count += 1

                # Save and print
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
                self.save_result(color_image, result, timestamp)
                self.print_analysis(result, analysis_time_ms)

                await asyncio.sleep(0.01)

        except KeyboardInterrupt:
            print("\n\n👋 Stopping analyzer...")

        except Exception as e:
            print(f"\n❌ Runtime error: {e}")
            import traceback
            traceback.print_exc()

        finally:
            await self.cleanup()

    async def cleanup(self):
        """Clean up resources"""
        self.is_running = False

        # Stop pipeline
        if self.pipeline_started:
            try:
                self.pipeline.stop()
                print("  ✓ Pipeline stopped")
                time.sleep(1)
            except Exception as e:
                print(f"  Warning: Pipeline stop error: {e}")

        # Print statistics
        elapsed = time.time() - self.start_time if self.start_time else 0

        print("\n" + "=" * 60)
        print("Statistics:")
        print(f"  Total frames:     {self.frame_count}")
        print(f"  Analyses:         {self.analysis_count}")
        print(f"  Duration:         {elapsed:.1f}s")

        if config.ENABLE_TOKEN_TRACKING and self.analysis_count > 0:
            avg_input = self.total_input_tokens / self.analysis_count
            avg_output = self.total_output_tokens / self.analysis_count
            print(f"  Avg tokens/call:  {avg_input:.0f} in / {avg_output:.0f} out")
            print(f"  Total tokens:     {self.total_input_tokens} in / {self.total_output_tokens} out")

            # Cost estimation
            input_cost = (self.total_input_tokens / 1_000_000) * 0.150
            output_cost = (self.total_output_tokens / 1_000_000) * 0.600
            print(f"  Estimated cost:   ${input_cost + output_cost:.4f}")

        print("=" * 60)
        print("✓ Analyzer stopped")


# ============================================================
# Main Entry Point
# ============================================================

async def main():
    """Entry point"""

    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        print("❌ Error: OPENAI_API_KEY not found")
        print("\n💡 Set it using one of:")
        print("   1. Create .env file with: OPENAI_API_KEY=your-api-key-here")
        print("   2. Or export: export OPENAI_API_KEY='your-api-key-here'")
        return

    analyzer = GPTRealsenseAnalyzer(api_key)

    try:
        await analyzer.run()
    except Exception as e:
        print(f"❌ Main error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 Exiting...")
