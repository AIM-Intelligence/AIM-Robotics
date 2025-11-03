"""
Backend Selection Module

Automatically selects between Python and C++ implementations
based on the SLAMRX_BACKEND environment variable.

Usage:
    # C++ backend (default, optimized)
    python3 live_slam.py

    # Or explicitly:
    SLAMRX_BACKEND=cpp python3 live_slam.py

    # Python backend (for testing/debugging)
    SLAMRX_BACKEND=py python3 live_slam.py

    # In code:
    from backend import LidarProtocol, ProtocolStats, FrameBuilder, Frame, FrameBuilderStats
"""

import os
import sys

# Determine backend from environment variable (default: cpp for best performance)
BACKEND_ENV = os.getenv("SLAMRX_BACKEND", "cpp").lower()
USE_CPP = BACKEND_ENV in ("cpp", "c++", "cxx")

if USE_CPP:
    # Try to load C++ backends
    try:
        # Protocol Parser (Phase 1)
        from lidar_protocol_cpp import (
            LidarProtocol as _LidarProtocol,
            ProtocolStats as _ProtocolStats,
            MAGIC, VERSION, HEADER_SIZE, POINT_SIZE, MAX_POINTS_PER_PACKET
        )

        # Frame Builder (Phase 2)
        from frame_builder_cpp import (
            FrameBuilder as _FrameBuilder,
            FrameBuilderStats as _FrameBuilderStats
        )

        # Export C++ classes
        LidarProtocol = _LidarProtocol
        ProtocolStats = _ProtocolStats
        FrameBuilder = _FrameBuilder
        FrameBuilderStats = _FrameBuilderStats

        # Frame is returned as dict from C++, so import Python Frame for type hints
        from frame_builder import Frame

        print(f"[BACKEND] ✓ Using C++ optimized backend", file=sys.stderr)
        print(f"[BACKEND]   - lidar_protocol_cpp (Phase 1)", file=sys.stderr)
        print(f"[BACKEND]   - frame_builder_cpp (Phase 2)", file=sys.stderr)
        BACKEND = "cpp"

    except ImportError as e:
        # Fallback to Python if C++ modules not available
        print(f"[BACKEND] ⚠  C++ backend not available: {e}", file=sys.stderr)
        print(f"[BACKEND] → Falling back to Python implementation", file=sys.stderr)

        from lidar_protocol import (
            LidarProtocol,
            ProtocolStats,
            LidarProtocol as _LidarProtocol
        )

        from frame_builder import (
            FrameBuilder,
            Frame,
            FrameBuilderStats
        )

        # Get constants from Python module
        MAGIC = _LidarProtocol.MAGIC
        VERSION = _LidarProtocol.VERSION
        HEADER_SIZE = _LidarProtocol.HEADER_SIZE
        POINT_SIZE = _LidarProtocol.POINT_SIZE
        MAX_POINTS_PER_PACKET = _LidarProtocol.MAX_POINTS_PER_PACKET

        BACKEND = "py"

else:
    # Use Python backend
    from lidar_protocol import (
        LidarProtocol,
        ProtocolStats,
        LidarProtocol as _LidarProtocol
    )

    from frame_builder import (
        FrameBuilder,
        Frame,
        FrameBuilderStats
    )

    # Get constants from Python module
    MAGIC = _LidarProtocol.MAGIC
    VERSION = _LidarProtocol.VERSION
    HEADER_SIZE = _LidarProtocol.HEADER_SIZE
    POINT_SIZE = _LidarProtocol.POINT_SIZE
    MAX_POINTS_PER_PACKET = _LidarProtocol.MAX_POINTS_PER_PACKET

    print(f"[BACKEND] Using Python backend (lidar_protocol + frame_builder)", file=sys.stderr)
    BACKEND = "py"


# Export all
__all__ = [
    "LidarProtocol",
    "ProtocolStats",
    "FrameBuilder",
    "Frame",
    "FrameBuilderStats",
    "MAGIC",
    "VERSION",
    "HEADER_SIZE",
    "POINT_SIZE",
    "MAX_POINTS_PER_PACKET",
    "BACKEND",
]
