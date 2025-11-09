#!/usr/bin/env python3
"""
GPT Vision + G1 Arm Control Integration (Python 3.8 Compatible)
Real-time scene analysis using OpenAI's GPT Vision API to control the Unitree G1 Arm.
Uses loop.run_in_executor for compatibility with Python 3.8 (Ubuntu 20.04).
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

# Unitree SDK 임포트
sys.path.insert(0, '/home/unitree/unitree_sdk2_python')
from unitree_sdk2py.core.channel import ChannelFactoryInitialize
from unitree_sdk2py.g1.arm.g1_arm_action_client import G1ArmActionClient

import config
import prompts # 업데이트된 prompts.py를 임포트

# Load environment variables
load_dotenv()

# ============================================================
# Arm 액션 정의 (제공된 전체 목록)
# ============================================================
ARM_ACTIONS = {
    # Kiss gestures
    "two-hand kiss": 11,
    "two hand kiss": 11,
    "kiss": 11,
    "left kiss": 12,
    "right kiss": 13,

    # Basic gestures
    "hands up": 15,
    "clap": 17,
    "high five": 18,
    "hug": 19,

    # Heart gestures
    "heart": 20,
    "right heart": 21,

    # Communication gestures
    "reject": 22,
    "no": 22,

    # Wave gestures
    "x-ray": 24,
    "xray": 24,
    "face wave": 25,
    "high wave": 26, 
    "wave": 26,      
    "shake hand": 27, 
    "shake": 27,      

    # Control
    "release": 99,
    "release arm": 99,
    
    # Internal
    "no_action": -1 
}

# ============================================================
# GPT Vision Analyzer
# ============================================================

class GPTRealsenseAnalyzer:
    def __init__(self, api_key):
        self.api_key = api_key
        self.client = AsyncOpenAI(api_key=api_key)
        self.pipeline = None
        self.pipeline_started = False
        self.arm_client = None
        self.arm_is_busy = False 
        self.is_running = False
        self.frame_count = 0
        self.analysis_count = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.start_time = None
        self.last_analysis_time = 0
        self.log_dir = Path(config.LOG_DIR)
        if config.SAVE_IMAGES or config.SAVE_RESPONSES:
            self.log_dir.mkdir(parents=True, exist_ok=True)

    def init_arm_client(self):
        """Initialize Unitree G1 Arm Client"""
        print("🦾 Initializing G1 Arm Client (DDS)...")
        try:
            ChannelFactoryInitialize(0, 'eth0')
            self.arm_client = G1ArmActionClient()
            self.arm_client.SetTimeout(10.0)
            self.arm_client.Init()
            print("  ✓ ArmClient ready")
            return True
        except Exception as e:
            print(f"❌ G1 Arm Client initialization failed: {e}")
            return False

    def init_realsense(self):
        """Initialize RealSense D435i camera"""
        print("🎥 Initializing RealSense D435i...")
        try:
            self.pipeline = rs.pipeline()
            rs_config = rs.config()
            
            rs_config.enable_stream(
                rs.stream.depth, config.REALSENSE_WIDTH, config.REALSENSE_HEIGHT,
                rs.format.z16, config.REALSENSE_FPS
            )
            rs_config.enable_stream(
                rs.stream.color, config.REALSENSE_WIDTH, config.REALSENSE_HEIGHT,
                rs.format.bgr8, config.REALSENSE_FPS
            )
            
            print(f"  - Streams: {config.REALSENSE_WIDTH}x{config.REALSENSE_HEIGHT} @ {config.REALSENSE_FPS}fps")
            print("  - Waiting for device to be ready...")
            time.sleep(1.0)
            
            profile = self.pipeline.start(rs_config)
            self.pipeline_started = True
            time.sleep(0.3)

            color_stream = profile.get_stream(rs.stream.color).as_video_stream_profile()
            intrinsics = color_stream.get_intrinsics()
            print(f"  ✓ Pipeline started")
            print(f"  - Focal length: fx={intrinsics.fx:.1f}, fy={intrinsics.fy:.1f}")

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
        depth_normalized = cv2.normalize(depth_image, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
        depth_colorized = cv2.applyColorMap(depth_normalized, cv2.COLORMAP_JET)
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

    async def analyze_frame(self, bgr_image, depth_image, depth_m, prompt_template):
        """Send frame to GPT Vision API for analysis"""
        prompt_text = prompts.build_prompt(
            prompt_template, 
            depth_m=depth_m, 
            include_depth_image=config.SEND_DEPTH_IMAGE
        )
        
        # Build content list
        content = [
            {"type": "text", "text": prompt_text},
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{self.encode_image(bgr_image)}",
                    "detail": config.IMAGE_DETAIL
                }
            }
        ]

        # Optionally add depth image
        if config.SEND_DEPTH_IMAGE and depth_image is not None:
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{self.encode_depth_image(depth_image)}",
                    "detail": config.IMAGE_DETAIL
                }
            })

        try:
            response = await self.client.chat.completions.create(
                model=config.OPENAI_MODEL,
                messages=[{"role": "user", "content": content}],
                max_tokens=config.MAX_TOKENS,
                temperature=config.TEMPERATURE
            )
            analysis = response.choices[0].message.content
            
            tokens_in = response.usage.prompt_tokens if hasattr(response, 'usage') else None
            tokens_out = response.usage.completion_tokens if hasattr(response, 'usage') else None

            if config.ENABLE_TOKEN_TRACKING and tokens_in is not None:
                self.total_input_tokens += tokens_in
                self.total_output_tokens += tokens_out

            return {
                "success": True, 
                "analysis": analysis, 
                "prompt": prompt_text, 
                "depth_m": depth_m,
                "tokens": {"input": tokens_in, "output": tokens_out}
            }
            
        except Exception as e:
            return {
                "success": False, 
                "error": str(e), 
                "prompt": prompt_text, 
                "depth_m": depth_m
            }


    async def execute_robot_action(self, action_command: str):
        """
        VLM 응답을 받아 로봇 팔 동작을 실행 (Python 3.8 호환 버전)
        """
        cmd = action_command.strip().lower()

        if self.arm_is_busy:
            print(f"🤖 Arm is busy. Skipping new command: '{cmd}'")
            return

        # 수정된 ARM_ACTIONS 딕셔너리를 여기서 사용
        if cmd in ARM_ACTIONS and cmd != "no_action":
            action_id = ARM_ACTIONS[cmd]
            print(f"🤖 VLM Decision: '{cmd}' (ID: {action_id}). Executing...")

            self.arm_is_busy = True
            
            try:
                # Python 3.8 호환을 위해 run_in_executor 사용
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(
                    None,  # 기본 ThreadPoolExecutor 사용
                    self.arm_client.ExecuteAction, # 실행할 동기(Blocking) 함수
                    action_id  # 해당 함수에 전달할 인자
                )

                if result == 0:
                    print(f"✓ Arm action '{cmd}' success!")
                    await asyncio.sleep(0.5) # 동작 완료 후 대기

                    # Auto release after action completes
                    if action_id != 99:  # Don't release after release command
                        print(f"🤖 Auto-releasing arm...")
                        release_result = await loop.run_in_executor(
                            None,
                            self.arm_client.ExecuteAction,
                            99  # Release action
                        )
                        if release_result == 0:
                            print(f"✓ Arm released")
                        else:
                            print(f"✗ Release failed with code: {release_result}")

                elif result == 7404:
                    print(f"✗ Error 7404: Cannot control arm. Check robot state (SELECT+Y).")
                    await asyncio.sleep(2.0)
                else:
                    print(f"✗ Arm action error code: {result}")
                    await asyncio.sleep(2.0)

            except Exception as e:
                print(f"Error during arm execution: {e}")
                import traceback
                traceback.print_exc()
            
            finally:
                self.arm_is_busy = False

        elif cmd == "no_action":
            pass # VLM이 NO_ACTION을 반환하면 아무것도 하지 않음
        else:
            # VLM이 프롬프트 목록에 없는 이상한 값을 반환한 경우
            print(f"⚠️ Unknown action from VLM: '{cmd}'")

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

            if config.ENABLE_TOKEN_TRACKING and result["tokens"].get("input"):
                print(f"\n📊 Tokens: {result['tokens']['input']} in / {result['tokens']['output']} out")
        else:
            print(f"\n❌ Error: {result['error']}")

        print("=" * 60)


    async def run(self):
        """Main run loop"""
        if not self.init_realsense():
            print("❌ Failed to initialize camera")
            return

        print("\n" + "=" * 60)
        print("🦾 GPT VISION + G1 ARM CONTROLLER (Python 3.8 Compatible)")
        print("=" * 60)
        print(f"  Model:         {config.OPENAI_MODEL}")
        print(f"  Detail:        {config.IMAGE_DETAIL}")
        print(f"  Resolution:    {config.REALSENSE_WIDTH}x{config.REALSENSE_HEIGHT}")
        print(f"  Depth Image:   {'Enabled' if config.SEND_DEPTH_IMAGE else 'Disabled'}")
        print("\n" + "=" * 60)
        print("Press Ctrl+C to stop")
        print("=" * 60)

        self.is_running = True
        self.start_time = time.time()

        try:
            while self.is_running:
                frames = self.pipeline.wait_for_frames()
                depth_frame = frames.get_depth_frame()
                color_frame = frames.get_color_frame()
                if not depth_frame or not color_frame:
                    continue

                self.frame_count += 1
                depth_image = np.asanyarray(depth_frame.get_data())
                color_image = np.asanyarray(color_frame.get_data())
                depth_m = self.get_center_depth(depth_frame)

                analysis_start = time.time()
                
                # [중요] 업데이트된 ARM_ACTION_DECISION_KR 프롬프트를 사용
                result = await self.analyze_frame(
                    color_image, depth_image, depth_m,
                    prompt_template=prompts.ARM_ACTION_DECISION_KR 
                )
                
                analysis_time_ms = (time.time() - analysis_start) * 1000
                self.analysis_count += 1

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
                self.save_result(color_image, result, timestamp)
                self.print_analysis(result, analysis_time_ms)

                if result["success"]:
                    action_command = result["analysis"].strip().lower()
                    # execute_robot_action이 새 ARM_ACTIONS 맵을 사용
                    await self.execute_robot_action(action_command)

                await asyncio.sleep(0.01) # 메인 루프가 CPU를 다 쓰지 않도록 잠시 대기

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
        if self.pipeline_started:
            try:
                self.pipeline.stop()
                print("  ✓ Pipeline stopped")
                time.sleep(1)
            except Exception as e:
                print(f"  Warning: Pipeline stop error: {e}")
        
        # Statistics 출력
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
            
            # (비용은 모델에 따라 다름, 예시)
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

    # Arm 클라이언트 초기화
    if not analyzer.init_arm_client():
        return

    # [중요] 로봇 준비 상태 확인
    print("\n" + "=" * 60)
    print("IMPORTANT: Robot must be in ready state!")
    print("Use hand controller: L1+UP, then R2+X")
    print("Or try: SELECT+Y to test if arm control works")
    print("=" * 60)
    
    try:
        input("Press Enter when robot is ready, or Ctrl+C to abort...")
    except KeyboardInterrupt:
        print("\nAborting...")
        return

    # 메인 루프 실행
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