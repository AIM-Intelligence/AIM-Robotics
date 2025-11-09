#!/usr/bin/env python3
"""
Microphone Device Finder
Automatically detects USB microphone ALSA device names
"""

import subprocess
import re

def find_usb_microphone():
    """Find USB microphone device using arecord -l"""
    print("=" * 60)
    print("🔍 Searching for USB Microphone...")
    print("=" * 60)

    try:
        # Run arecord -l to list all capture devices
        result = subprocess.run(['arecord', '-l'], capture_output=True, text=True)
        output = result.stdout

        print("\n📋 Raw output from 'arecord -l':")
        print(output)

        # Parse the output to find USB devices
        lines = output.split('\n')
        usb_devices = []

        for line in lines:
            # Look for lines like: card 0: N550 [ABKO N550], device 0: USB Audio [USB Audio]
            match = re.search(r'card (\d+): (\w+) \[(.*?)\].*device (\d+):', line)
            if match:
                card_num = match.group(1)
                card_id = match.group(2)
                card_name = match.group(3)
                device_num = match.group(4)

                # Check if it's a USB device (look for USB in the name or specific keywords)
                if 'USB' in line.upper() or any(keyword in card_name.upper() for keyword in ['N550', 'ABKO', 'HEADSET', 'MIC']):
                    usb_devices.append({
                        'card_num': card_num,
                        'card_id': card_id,
                        'card_name': card_name,
                        'device_num': device_num
                    })

        if not usb_devices:
            print("\n❌ No USB microphone found!")
            return None

        print("\n" + "=" * 60)
        print("✅ Found USB Microphone(s):")
        print("=" * 60)

        for i, dev in enumerate(usb_devices, 1):
            print(f"\n📍 Device {i}:")
            print(f"   Name: {dev['card_name']}")
            print(f"   Card Number: {dev['card_num']}")
            print(f"   Card ID: {dev['card_id']}")
            print(f"   Device Number: {dev['device_num']}")
            print(f"\n   🎯 ALSA Device Names:")
            print(f"      hw:{dev['card_num']},{dev['device_num']}")
            print(f"      plughw:{dev['card_num']},{dev['device_num']}")
            print(f"      hw:CARD={dev['card_id']},DEV={dev['device_num']}")
            print(f"      plughw:CARD={dev['card_id']},DEV={dev['device_num']}")

        # Return the first USB device found
        primary_device = usb_devices[0]

        print("\n" + "=" * 60)
        print("💡 Recommended Device Strings for Python Code:")
        print("=" * 60)
        print(f"\n   Option 1 (Numeric): 'plughw:{primary_device['card_num']},{primary_device['device_num']}'")
        print(f"   Option 2 (Named):   'plughw:CARD={primary_device['card_id']},DEV={primary_device['device_num']}'")
        print(f"   Option 3 (Simple):  'hw:CARD={primary_device['card_id']},DEV={primary_device['device_num']}'")
        print("\n   ⭐ Best choice: Option 2 (named) - works even if card order changes\n")

        return primary_device

    except FileNotFoundError:
        print("❌ Error: 'arecord' command not found. Please install alsa-utils.")
        return None
    except Exception as e:
        print(f"❌ Error: {e}")
        return None


def test_microphone_device(device_string):
    """Test if microphone device works"""
    print("=" * 60)
    print(f"🧪 Testing microphone: {device_string}")
    print("=" * 60)

    try:
        print("\n🎤 Recording 2 seconds of audio...")
        result = subprocess.run(
            ['arecord', '-D', device_string, '-f', 'cd', '-d', '2', '/tmp/test_mic.wav'],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode == 0:
            print("✅ Recording successful!")
            print(f"   Test file saved: /tmp/test_mic.wav")

            # Check file size
            import os
            if os.path.exists('/tmp/test_mic.wav'):
                size = os.path.getsize('/tmp/test_mic.wav')
                print(f"   File size: {size} bytes")
                if size > 1000:
                    print("   ✅ Microphone is working!")
                    return True
                else:
                    print("   ⚠️  File too small - microphone may not be working")
                    return False
        else:
            print(f"❌ Recording failed!")
            print(f"   Error: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        print("❌ Recording timed out!")
        return False
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False


if __name__ == "__main__":
    # Find the microphone
    device = find_usb_microphone()

    if device:
        # Test it
        device_string = f"plughw:CARD={device['card_id']},DEV={device['device_num']}"
        test_microphone_device(device_string)

        print("\n" + "=" * 60)
        print("📝 Copy this line to your Python code:")
        print("=" * 60)
        print(f"\n   device='plughw:CARD={device['card_id']},DEV={device['device_num']}'\n")
