#!/usr/bin/env python3
"""
G1 Arm Only Control
LocoClient를 사용하지 않고 팔만 제어
"""
import sys
import time
sys.path.insert(0, '/home/unitree/unitree_sdk2_python')

from unitree_sdk2py.core.channel import ChannelFactoryInitialize
from unitree_sdk2py.g1.arm.g1_arm_action_client import G1ArmActionClient

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
}

def main():
    print("=" * 60)
    print("G1 Arm Only Control")
    print("=" * 60)
    print("\nIMPORTANT: Robot must be in ready state!")
    print("Use hand controller: L1+UP, then R2+X")
    print("Or try: SELECT+Y to test if arm control works\n")

    input("Press Enter when robot is ready, or Ctrl+C to abort...")

    # DDS 초기화
    print("\nInitializing...")
    ChannelFactoryInitialize(0, 'eth0')

    # Arm 클라이언트만 초기화
    arm_client = G1ArmActionClient()
    arm_client.SetTimeout(10.0)
    arm_client.Init()
    print("✓ ArmClient ready\n")

    print("Available gestures:")
    print("  Kiss: kiss/two-hand kiss, left kiss, right kiss")
    print("  Basic: hands up, clap, high five, hug")
    print("  Heart: heart, right heart")
    print("  Wave: wave/high wave, face wave, shake/shake hand")
    print("  Other: reject/no, x-ray/xray")
    print("  Control: release/release arm, quit")

    while True:
        try:
            cmd = input("\nArm> ").strip().lower()

            if cmd in ['q', 'quit', 'exit']:
                break

            if cmd in ARM_ACTIONS:
                action_id = ARM_ACTIONS[cmd]
                print(f"→ Executing {cmd} (ID: {action_id})...")
                result = arm_client.ExecuteAction(action_id)

                if result == 0:
                    print(f"✓ Success!")
                    time.sleep(4)
                elif result == 7404:
                    print(f"✗ Error 7404: Cannot control arm")
                    print("   Possible solutions:")
                    print("   1. Use hand controller: SELECT+Y (wave)")
                    print("   2. Restart robot completely")
                    print("   3. Don't run any loco scripts before this")
                else:
                    print(f"✗ Error code: {result}")
            else:
                print(f"Unknown command. Available: {list(ARM_ACTIONS.keys())}")

        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    main()
