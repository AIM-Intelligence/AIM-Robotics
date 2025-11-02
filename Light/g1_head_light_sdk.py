#!/usr/bin/env python3
"""
Unitree G1 Head Light Control using Official SDK

This script uses the official Unitree SDK2 AudioClient.LedControl() method
to control the G1 robot's RGB LED head lights.

Usage:
    python3 g1_head_light_sdk.py <network_interface>

Example:
    python3 g1_head_light_sdk.py eth0

Date: 2025-10-30
"""

import time
import sys
from unitree_sdk2py.core.channel import ChannelFactoryInitialize
from unitree_sdk2py.g1.audio.g1_audio_client import AudioClient


class G1HeadLightSDK:
    """
    G1 Head Light controller using official SDK AudioClient.

    This class provides convenient methods to control the RGB LED head lights
    on the Unitree G1 robot using the LedControl() API.
    """

    # Predefined colors
    COLORS = {
        'off': (0, 0, 0),
        'red': (255, 0, 0),
        'green': (0, 255, 0),
        'blue': (0, 0, 255),
        'yellow': (255, 255, 0),
        'cyan': (0, 255, 255),
        'magenta': (255, 0, 255),
        'white': (255, 255, 255),
        'orange': (255, 165, 0),
        'purple': (128, 0, 128),
        'pink': (255, 192, 203),
        'lime': (0, 255, 0),
        'navy': (0, 0, 128),
        'teal': (0, 128, 128),
    }

    def __init__(self, network_interface: str = "eth0"):
        """
        Initialize G1 Head Light controller.

        Args:
            network_interface: Network interface name (e.g., "eth0", "enp2s0")
        """
        # Initialize DDS channel
        ChannelFactoryInitialize(0, network_interface)

        # Create and initialize audio client
        self.audio_client = AudioClient()
        self.audio_client.SetTimeout(10.0)
        self.audio_client.Init()

        print(f"G1 Head Light SDK initialized on {network_interface}")

    def set_color(self, r: int, g: int, b: int) -> int:
        """
        Set head light color using RGB values.

        Args:
            r: Red value (0-255)
            g: Green value (0-255)
            b: Blue value (0-255)

        Returns:
            Status code (0 = success)
        """
        # Clamp values to valid range
        r = max(0, min(255, r))
        g = max(0, min(255, g))
        b = max(0, min(255, b))

        code = self.audio_client.LedControl(r, g, b)
        if code == 0:
            print(f"✓ Set color to RGB({r}, {g}, {b})")
        else:
            print(f"✗ Failed to set color: code {code}")
        return code

    def set_color_name(self, color_name: str) -> int:
        """
        Set head light color using predefined color names.

        Args:
            color_name: Color name (e.g., 'red', 'green', 'blue')

        Returns:
            Status code (0 = success)
        """
        color_name = color_name.lower()
        if color_name not in self.COLORS:
            print(f"✗ Unknown color: {color_name}")
            print(f"Available colors: {', '.join(self.COLORS.keys())}")
            return -1

        r, g, b = self.COLORS[color_name]
        print(f"Setting color to {color_name.upper()}", end=" ")
        return self.set_color(r, g, b)

    def turn_off(self) -> int:
        """Turn off head light."""
        print("Turning OFF head light")
        return self.set_color(0, 0, 0)

    def blink(self, r: int, g: int, b: int, times: int = 3, interval: float = 0.5) -> None:
        """
        Blink head light with specified color.

        Args:
            r, g, b: RGB color values
            times: Number of blinks
            interval: Interval between blinks in seconds
        """
        print(f"Blinking RGB({r}, {g}, {b}) {times} times...")
        for i in range(times):
            self.set_color(r, g, b)
            time.sleep(interval)
            self.turn_off()
            time.sleep(interval)

    def blink_color(self, color_name: str, times: int = 3, interval: float = 0.5) -> None:
        """
        Blink head light with named color.

        Args:
            color_name: Color name
            times: Number of blinks
            interval: Interval between blinks in seconds
        """
        if color_name.lower() not in self.COLORS:
            print(f"✗ Unknown color: {color_name}")
            return

        r, g, b = self.COLORS[color_name.lower()]
        self.blink(r, g, b, times, interval)

    def rainbow_cycle(self, duration: float = 5.0, steps: int = 50) -> None:
        """
        Cycle through rainbow colors.

        Args:
            duration: Total duration in seconds
            steps: Number of color steps
        """
        print(f"Rainbow cycle for {duration} seconds...")
        interval = duration / steps

        for i in range(steps):
            # HSV to RGB conversion for rainbow effect
            hue = (i / steps) * 360
            r, g, b = self._hsv_to_rgb(hue, 1.0, 1.0)
            self.set_color(r, g, b)
            time.sleep(interval)

    def pulse(self, r: int, g: int, b: int, duration: float = 3.0, steps: int = 30) -> None:
        """
        Pulse effect (fade in and out).

        Args:
            r, g, b: Base RGB color
            duration: Total duration in seconds
            steps: Number of brightness steps
        """
        print(f"Pulsing RGB({r}, {g}, {b}) for {duration} seconds...")
        interval = duration / (steps * 2)

        # Fade in
        for i in range(steps):
            brightness = i / steps
            self.set_color(int(r * brightness), int(g * brightness), int(b * brightness))
            time.sleep(interval)

        # Fade out
        for i in range(steps, -1, -1):
            brightness = i / steps
            self.set_color(int(r * brightness), int(g * brightness), int(b * brightness))
            time.sleep(interval)

    def strobe(self, r: int, g: int, b: int, duration: float = 2.0, frequency: float = 10.0) -> None:
        """
        Strobe effect (rapid flashing).

        Args:
            r, g, b: RGB color
            duration: Total duration in seconds
            frequency: Flash frequency in Hz
        """
        print(f"Strobe effect at {frequency} Hz for {duration} seconds...")
        interval = 1.0 / (frequency * 2)
        end_time = time.time() + duration

        while time.time() < end_time:
            self.set_color(r, g, b)
            time.sleep(interval)
            self.turn_off()
            time.sleep(interval)

    def gradient_transition(self, from_color: tuple, to_color: tuple, duration: float = 2.0, steps: int = 30) -> None:
        """
        Smooth gradient transition between two colors.

        Args:
            from_color: Starting RGB tuple (r, g, b)
            to_color: Ending RGB tuple (r, g, b)
            duration: Transition duration in seconds
            steps: Number of intermediate steps
        """
        r1, g1, b1 = from_color
        r2, g2, b2 = to_color

        print(f"Gradient transition from RGB{from_color} to RGB{to_color}...")
        interval = duration / steps

        for i in range(steps + 1):
            t = i / steps
            r = int(r1 + (r2 - r1) * t)
            g = int(g1 + (g2 - g1) * t)
            b = int(b1 + (b2 - b1) * t)
            self.set_color(r, g, b)
            time.sleep(interval)

    def police_lights(self, duration: float = 5.0) -> None:
        """Police siren light effect (red/blue alternating)."""
        print("Police lights effect...")
        end_time = time.time() + duration

        while time.time() < end_time:
            self.set_color(255, 0, 0)  # Red
            time.sleep(0.3)
            self.set_color(0, 0, 255)  # Blue
            time.sleep(0.3)

    def heartbeat(self, r: int, g: int, b: int, times: int = 3) -> None:
        """
        Heartbeat pattern (double pulse).

        Args:
            r, g, b: RGB color
            times: Number of heartbeat cycles
        """
        print(f"Heartbeat pattern {times} times...")
        for _ in range(times):
            # First beat
            self.set_color(r, g, b)
            time.sleep(0.15)
            self.turn_off()
            time.sleep(0.1)
            # Second beat
            self.set_color(r, g, b)
            time.sleep(0.15)
            self.turn_off()
            time.sleep(0.6)

    def _hsv_to_rgb(self, h: float, s: float, v: float) -> tuple:
        """
        Convert HSV to RGB.

        Args:
            h: Hue (0-360)
            s: Saturation (0-1)
            v: Value (0-1)

        Returns:
            (r, g, b) tuple with values 0-255
        """
        h = h / 60.0
        i = int(h)
        f = h - i
        p = v * (1 - s)
        q = v * (1 - s * f)
        t = v * (1 - s * (1 - f))

        if i == 0:
            r, g, b = v, t, p
        elif i == 1:
            r, g, b = q, v, p
        elif i == 2:
            r, g, b = p, v, t
        elif i == 3:
            r, g, b = p, q, v
        elif i == 4:
            r, g, b = t, p, v
        else:
            r, g, b = v, p, q

        return (int(r * 255), int(g * 255), int(b * 255))


def demo_basic_colors(controller: G1HeadLightSDK):
    """Demo basic color setting."""
    print("\n" + "="*60)
    print("DEMO 1: Basic Colors")
    print("="*60)

    colors = ['red', 'green', 'blue', 'yellow', 'cyan', 'magenta', 'white']

    for color in colors:
        controller.set_color_name(color)
        time.sleep(1)

    controller.turn_off()
    time.sleep(0.5)


def demo_blink_patterns(controller: G1HeadLightSDK):
    """Demo blinking patterns."""
    print("\n" + "="*60)
    print("DEMO 2: Blink Patterns")
    print("="*60)

    print("\n1. Red blink:")
    controller.blink_color('red', times=3, interval=0.5)

    print("\n2. Green fast blink:")
    controller.blink_color('green', times=5, interval=0.2)

    print("\n3. Blue slow blink:")
    controller.blink_color('blue', times=2, interval=1.0)


def demo_effects(controller: G1HeadLightSDK):
    """Demo special effects."""
    print("\n" + "="*60)
    print("DEMO 3: Special Effects")
    print("="*60)

    print("\n1. Rainbow cycle:")
    controller.rainbow_cycle(duration=5.0)

    print("\n2. Red pulse:")
    controller.pulse(255, 0, 0, duration=3.0)

    print("\n3. Green strobe:")
    controller.strobe(0, 255, 0, duration=2.0, frequency=5.0)

    print("\n4. Police lights:")
    controller.police_lights(duration=3.0)

    print("\n5. Heartbeat (cyan):")
    controller.heartbeat(0, 255, 255, times=3)

    controller.turn_off()


def demo_gradients(controller: G1HeadLightSDK):
    """Demo gradient transitions."""
    print("\n" + "="*60)
    print("DEMO 4: Gradient Transitions")
    print("="*60)

    transitions = [
        ('red', 'blue'),
        ('blue', 'green'),
        ('green', 'yellow'),
        ('yellow', 'red'),
    ]

    for from_color, to_color in transitions:
        print(f"\nTransition: {from_color} → {to_color}")
        controller.gradient_transition(
            controller.COLORS[from_color],
            controller.COLORS[to_color],
            duration=2.0
        )

    controller.turn_off()


def interactive_mode(controller: G1HeadLightSDK):
    """Interactive control mode."""
    print("\n" + "="*60)
    print("Interactive Head Light Control")
    print("="*60)
    print("\nCommands:")
    print("  <color_name>     - Set color (e.g., 'red', 'blue')")
    print("  rgb R G B        - Set RGB values (e.g., 'rgb 255 128 0')")
    print("  off              - Turn off")
    print("  blink <color>    - Blink with color")
    print("  rainbow          - Rainbow cycle")
    print("  pulse <color>    - Pulse effect")
    print("  police           - Police lights")
    print("  heartbeat <color>- Heartbeat pattern")
    print("  colors           - List available colors")
    print("  quit             - Exit")
    print()

    while True:
        try:
            cmd = input("Command> ").strip().lower()

            if cmd == 'quit' or cmd == 'exit' or cmd == 'q':
                controller.turn_off()
                break
            elif cmd == 'off':
                controller.turn_off()
            elif cmd == 'colors':
                print("Available colors:")
                print(", ".join(controller.COLORS.keys()))
            elif cmd == 'rainbow':
                controller.rainbow_cycle()
            elif cmd == 'police':
                controller.police_lights()
            elif cmd.startswith('rgb '):
                parts = cmd.split()
                if len(parts) == 4:
                    try:
                        r, g, b = int(parts[1]), int(parts[2]), int(parts[3])
                        controller.set_color(r, g, b)
                    except ValueError:
                        print("Invalid RGB values")
                else:
                    print("Usage: rgb R G B")
            elif cmd.startswith('blink '):
                color = cmd.split()[1]
                controller.blink_color(color, times=3)
            elif cmd.startswith('pulse '):
                color = cmd.split()[1]
                if color in controller.COLORS:
                    r, g, b = controller.COLORS[color]
                    controller.pulse(r, g, b)
            elif cmd.startswith('heartbeat '):
                color = cmd.split()[1]
                if color in controller.COLORS:
                    r, g, b = controller.COLORS[color]
                    controller.heartbeat(r, g, b)
            elif cmd in controller.COLORS:
                controller.set_color_name(cmd)
            else:
                print(f"Unknown command: {cmd}")

        except KeyboardInterrupt:
            print("\nExiting...")
            controller.turn_off()
            break
        except Exception as e:
            print(f"Error: {e}")


def main():
    """Main function."""
    if len(sys.argv) < 2:
        print(f"Usage: python3 {sys.argv[0]} <network_interface> [mode]")
        print(f"\nExample:")
        print(f"  python3 {sys.argv[0]} eth0")
        print(f"  python3 {sys.argv[0]} eth0 demo")
        print(f"  python3 {sys.argv[0]} eth0 interactive")
        print(f"\nModes:")
        print(f"  demo         - Run all demos (default)")
        print(f"  interactive  - Interactive control mode")
        print(f"  colors       - Demo basic colors only")
        print(f"  blink        - Demo blink patterns only")
        print(f"  effects      - Demo special effects only")
        print(f"  gradients    - Demo gradients only")
        sys.exit(1)

    network_interface = sys.argv[1]
    mode = sys.argv[2] if len(sys.argv) > 2 else "demo"

    print("="*60)
    print("Unitree G1 Head Light Control (SDK)")
    print("="*60)
    print()

    # Initialize controller
    controller = G1HeadLightSDK(network_interface)

    try:
        if mode == "interactive":
            interactive_mode(controller)
        elif mode == "colors":
            demo_basic_colors(controller)
        elif mode == "blink":
            demo_blink_patterns(controller)
        elif mode == "effects":
            demo_effects(controller)
        elif mode == "gradients":
            demo_gradients(controller)
        elif mode == "demo":
            demo_basic_colors(controller)
            demo_blink_patterns(controller)
            demo_effects(controller)
            demo_gradients(controller)
        else:
            print(f"Unknown mode: {mode}")
            sys.exit(1)

        print("\n" + "="*60)
        print("Demo completed successfully!")
        print("="*60)

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        controller.turn_off()
    except Exception as e:
        print(f"\nError: {e}")
        controller.turn_off()
        raise


if __name__ == "__main__":
    main()
