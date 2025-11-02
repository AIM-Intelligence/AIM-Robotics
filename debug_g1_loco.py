#!/usr/bin/env python3
"""
Test script to properly control G1 using LocoClient
This ensures the robot is in FSM 200 before sending Move commands
"""
import sys
import time
sys.path.insert(0, '/home/unitree/unitree_sdk2_python')

from unitree_sdk2py.core.channel import ChannelFactoryInitialize
from unitree_sdk2py.g1.loco.g1_loco_client import LocoClient
from unitree_sdk2py.g1.loco.g1_loco_api import ROBOT_API_ID_LOCO_GET_FSM_ID, ROBOT_API_ID_LOCO_GET_FSM_MODE
import json

def get_fsm_id(client):
    """Get current FSM ID"""
    code, data = client._Call(ROBOT_API_ID_LOCO_GET_FSM_ID, "{}")
    if code == 0 and data:
        return json.loads(data).get("data")
    return None

def get_fsm_mode(client):
    """Get current FSM mode (0=feet loaded, 2=feet unloaded)"""
    code, data = client._Call(ROBOT_API_ID_LOCO_GET_FSM_MODE, "{}")
    if code == 0 and data:
        return json.loads(data).get("data")
    return None

def ensure_fsm_200(client):
    """
    Ensure robot is in FSM 200 (Start state) where Move commands work.
    This is the proper sequence to transition from any state to FSM 200.
    """
    current_fsm = get_fsm_id(client)
    current_mode = get_fsm_mode(client)

    print(f"Current FSM ID: {current_fsm}, Mode: {current_mode}")

    # If already in FSM 200 and feet loaded, we're good
    if current_fsm == 200 and current_mode == 0:
        print("✓ Already in FSM 200 (ready for Move commands)")
        return True

    print("\nTransitioning to FSM 200...")
    print("WARNING: Robot will stand up! Ensure it's safe to do so.")
    input("Press Enter to continue...")

    # Step 1: Damp
    print("1. Setting to Damp...")
    client.Damp()
    time.sleep(1)
    print(f"   FSM: {get_fsm_id(client)}")

    # Step 2: Stand up (FSM 4)
    print("2. Standing up...")
    client.SetFsmId(4)
    time.sleep(2)
    print(f"   FSM: {get_fsm_id(client)}, Mode: {get_fsm_mode(client)}")

    # Step 3: Set stand height gradually
    print("3. Setting stand height...")
    for height in [0.1, 0.2, 0.3]:
        client.SetStandHeight(height)
        time.sleep(2)
        mode = get_fsm_mode(client)
        print(f"   Height {height:.1f}m, Mode: {mode}")
        if mode == 0:  # Feet loaded
            break

    # Step 4: Balance stand
    print("4. Activating balance stand...")
    client.BalanceStand(0)  # 0 = static balance
    time.sleep(1)
    print(f"   FSM: {get_fsm_id(client)}")

    # Step 5: Start (FSM 200)
    print("5. Transitioning to FSM 200 (Start)...")
    client.Start()
    time.sleep(1)

    final_fsm = get_fsm_id(client)
    print(f"   Final FSM: {final_fsm}")

    if final_fsm == 200:
        print("✓ Successfully reached FSM 200!")
        return True
    else:
        print(f"✗ Failed to reach FSM 200 (got {final_fsm})")
        return False

def main():
    print("G1 LocoClient Test - Proper FSM Transition")
    print("=" * 50)

    # Initialize
    ChannelFactoryInitialize(0, 'eth0')

    client = LocoClient()
    client.SetTimeout(10.0)
    client.Init()
    print("✓ LocoClient initialized\n")

    # Ensure we're in FSM 200
    if not ensure_fsm_200(client):
        print("\nFailed to reach FSM 200. Exiting.")
        return

    print("\n" + "=" * 50)
    print("Robot is now ready for Move commands!")
    print("=" * 50)

    # Now test move commands
    try:
        # 전진 0.20 m/s로 3초
        client.Move(1, 0.00, 0.00)
        client.StopMove()
        time.sleep(0.5)

        # # 후진 0.15 m/s로 2초
        client.Move(1, 0.00, 0.00)
        time.sleep(0.5)
        client.StopMove()
        time.sleep(0.5)

        # 제자리 회전 0.30 rad/s로 2초 (반시계+)
        client.Move(0.00, 0.00, 0.30)
        time.sleep(2.0)
        client.StopMove()

        print("\nFinal: Stop")
        client.StopMove()

        print("\n✓ All tests completed successfully!")
        print(f"Final FSM: {get_fsm_id(client)}")

    except KeyboardInterrupt:
        print("\n\nInterrupted! Stopping robot...")
        client.StopMove()
    except Exception as e:
        print(f"\nError: {e}")
        client.StopMove()

if __name__ == "__main__":
    main()
