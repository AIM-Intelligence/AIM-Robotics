#!/usr/bin/env python3
"""
Debug script for G1 Arm Control using G1ArmActionClient
Similar to debug_g1_loco.py but for arm actions
Based on OM1 implementation
"""
import sys
import time
sys.path.insert(0, '/home/unitree/unitree_sdk2_python')

from unitree_sdk2py.core.channel import ChannelFactoryInitialize
from unitree_sdk2py.g1.arm.g1_arm_action_client import G1ArmActionClient

class ArmAction:
    """Arm actions based on OM1 implementation"""
    IDLE = "idle"
    LEFT_KISS = "left kiss"
    RIGHT_KISS = "right kiss"
    CLAP = "clap"
    HIGH_FIVE = "high five"
    SHAKE_HAND = "shake hand"
    HEART = "heart"
    HIGH_WAVE = "high wave"
    FACE_WAVE = "face wave"
    HANDS_UP = "hands up"
    HUG = "hug"
    RELEASE = "release arm"

# Action name to ID mapping (from OM1 and SDK)
ACTION_MAP = {
    "idle": None,
    "left kiss": 12,
    "right kiss": 13,
    "clap": 17,
    "high five": 18,
    "shake hand": 27,
    "heart": 20,
    "high wave": 26,
    "face wave": 25,
    "hands up": 15,
    "hug": 19,
    "release arm": 99,
}

class G1ArmController:
    def __init__(self, network_interface='eth0'):
        """Initialize G1 Arm Controller"""
        print(f"Initializing G1 Arm Controller on {network_interface}...")
        
        # Initialize DDS channel
        ChannelFactoryInitialize(0, network_interface)
        
        # Initialize arm client
        try:
            self.client = G1ArmActionClient()
            self.client.SetTimeout(10.0)
            self.client.Init()
            print("✓ G1ArmActionClient initialized successfully")
            
            # Get available actions
            code, data = self.client.GetActionList()
            if code == 0:
                print(f"✓ Got action list (code: {code})")
                if data and 'actions' in data:
                    print(f"  Available actions: {len(data['actions'])} total")
            else:
                print(f"⚠ GetActionList returned code: {code}")
                
        except Exception as e:
            print(f"✗ Failed to initialize G1ArmActionClient: {e}")
            raise
    
    def execute_action(self, action_name):
        """Execute an arm action by name"""
        if action_name not in ACTION_MAP:
            print(f"✗ Unknown action: {action_name}")
            print(f"Available actions: {list(ACTION_MAP.keys())}")
            return False
        
        action_id = ACTION_MAP[action_name]
        
        if action_id is None:
            print("ℹ Idle action - no movement")
            return True
        
        print(f"\nExecuting action: '{action_name}' (ID: {action_id})")
        
        try:
            result = self.client.ExecuteAction(action_id)
            
            if result == 0:
                print(f"✓ Action executed successfully (code: {result})")
                return True
            elif result == 7404:
                print(f"✗ Action failed with code 7404 - Service unavailable or wrong state")
                print("  Possible reasons:")
                print("  - Robot not in correct mode")
                print("  - Arm service not enabled")
                print("  - Need to release motion_switcher first")
                return False
            else:
                print(f"✗ Action failed with code: {result}")
                return False
                
        except Exception as e:
            print(f"✗ Exception executing action: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def list_actions(self):
        """List all available actions"""
        print("\nAvailable Arm Actions:")
        print("-" * 40)
        for action_name, action_id in ACTION_MAP.items():
            if action_id is None:
                print(f"  {action_name:20s} - No movement")
            else:
                print(f"  {action_name:20s} - ID: {action_id}")
        print("-" * 40)

def main():
    print("=" * 60)
    print("G1 Arm Controller - Debug Tool")
    print("=" * 60)
    print()
    
    # Initialize controller
    try:
        arm = G1ArmController('eth0')
    except Exception as e:
        print(f"\nFailed to initialize arm controller: {e}")
        sys.exit(1)
    
    print("\n" + "=" * 60)
    
    # Interactive mode
    if len(sys.argv) > 1:
        # Command line mode
        action = ' '.join(sys.argv[1:])
        arm.execute_action(action)
    else:
        # Interactive mode
        arm.list_actions()
        print("\nInteractive Mode - Enter action name (or 'q' to quit)")
        print("Example: high wave")
        print()
        
        while True:
            try:
                user_input = input("\nAction> ").strip().lower()
                
                if user_input in ['q', 'quit', 'exit']:
                    print("Exiting...")
                    break
                
                if user_input == 'list':
                    arm.list_actions()
                    continue
                
                if user_input == '':
                    continue
                
                # Execute action
                success = arm.execute_action(user_input)
                
                if success and user_input != 'idle':
                    print("Waiting for action to complete...")
                    time.sleep(5)  # Wait for action to complete
                    
                    # Auto release after some actions
                    if user_input in ['high five', 'shake hand', 'heart', 'hands up']:
                        print("Releasing arm...")
                        arm.execute_action('release arm')
                        time.sleep(1)
                        
            except KeyboardInterrupt:
                print("\n\nInterrupted!")
                break
            except Exception as e:
                print(f"\nError: {e}")

if __name__ == "__main__":
    main()
