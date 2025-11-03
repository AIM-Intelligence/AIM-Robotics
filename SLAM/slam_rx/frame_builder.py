"""
Frame Builder - Time-based Point Cloud Accumulator

Accumulates LiDAR packets into frames based on device timestamps.
Frames are closed when time window expires (frame_period_s).
"""

import numpy as np
from typing import Optional, Dict
from dataclasses import dataclass


@dataclass
class Frame:
    """Point cloud frame with metadata"""
    xyz: np.ndarray          # (N, 3) coordinates in meters
    start_ts_ns: int         # Frame start timestamp (ns)
    end_ts_ns: int           # Frame end timestamp (ns)
    seq_first: int           # First packet sequence number
    seq_last: int            # Last packet sequence number
    pkt_count: int           # Number of packets in frame
    point_count: int         # Total points in frame

    def duration_s(self) -> float:
        """Frame duration in seconds"""
        return (self.end_ts_ns - self.start_ts_ns) / 1e9

    def __repr__(self):
        return (f"Frame(pts={self.point_count}, pkts={self.pkt_count}, "
                f"dur={self.duration_s():.3f}s, seq={self.seq_first}-{self.seq_last})")


class FrameBuilderStats:
    """Statistics for frame building"""

    def __init__(self):
        self.frames_built = 0
        self.packets_added = 0
        self.points_added = 0
        self.late_packets = 0       # Packets with ts < current_frame_start
        self.seq_gaps = 0            # Detected sequence gaps
        self.seq_reorders = 0        # Out-of-order packets
        self.overflow_frames = 0     # Frames exceeding max_frame_points

    def reset(self):
        """Reset all counters"""
        self.__init__()

    def __repr__(self):
        return (f"FrameBuilderStats(frames={self.frames_built}, pkts={self.packets_added}, "
                f"pts={self.points_added}, late={self.late_packets}, "
                f"gaps={self.seq_gaps}, reorder={self.seq_reorders}, overflow={self.overflow_frames})")


class FrameBuilder:
    """Time-based frame accumulator"""

    def __init__(self,
                 frame_period_s: float = 0.05,
                 max_frame_points: int = 120000,
                 stats: Optional[FrameBuilderStats] = None):
        """
        Initialize frame builder

        Args:
            frame_period_s: Frame duration in seconds (default: 0.05 = 20Hz)
            max_frame_points: Safety limit for points per frame (default: 120k)
            stats: Statistics object (creates new if None)
        """
        self.frame_period_s = frame_period_s
        self.frame_period_ns = int(frame_period_s * 1e9)
        self.max_frame_points = max_frame_points
        self.stats = stats if stats is not None else FrameBuilderStats()

        # Current frame state
        self.current_frame_start_ts: Optional[int] = None
        self.current_frame_end_ts: Optional[int] = None
        self.current_points = []  # List of xyz arrays
        self.current_seq_first: Optional[int] = None
        self.current_seq_last: Optional[int] = None
        self.current_pkt_count = 0

        # Sequence tracking
        self.last_seq: Optional[int] = None

    def add_packet(self, device_ts_ns: int, points_xyz: np.ndarray, seq: int,
                   debug: bool = False) -> Optional[Frame]:
        """
        Add a packet to the current frame

        Args:
            device_ts_ns: Device timestamp in nanoseconds
            points_xyz: Point cloud (N, 3) array
            seq: Packet sequence number
            debug: Enable debug logging

        Returns:
            Completed Frame if time window closed, else None
        """
        # Initialize first frame
        if self.current_frame_start_ts is None:
            self._start_new_frame(device_ts_ns, seq, debug)

        # Check if packet is late (timestamp earlier than current frame start)
        if device_ts_ns < self.current_frame_start_ts:  # type: ignore[operator]
            self.stats.late_packets += 1
            if debug:
                delta_ms = (self.current_frame_start_ts - device_ts_ns) / 1e6  # type: ignore[operator]
                print(f"[FRAME] ⚠ Late packet: seq={seq}, -{delta_ms:.1f}ms (discarded)")
            return None

        # Check if we need to close current frame
        if device_ts_ns >= self.current_frame_start_ts + self.frame_period_ns:  # type: ignore[operator]
            completed_frame = self._close_current_frame(debug)
            self._start_new_frame(device_ts_ns, seq, debug)

            # Add the packet to the new frame after closing the old one
            return self._add_to_current_frame(device_ts_ns, points_xyz, seq, debug) or completed_frame
        else:
            # Add to current frame
            self._add_to_current_frame(device_ts_ns, points_xyz, seq, debug)
            return None

    def _add_to_current_frame(self, device_ts_ns: int, points_xyz: np.ndarray,
                             seq: int, debug: bool) -> Optional[Frame]:
        """Internal: Add packet to current frame"""
        # Check for sequence gaps/reorder
        if self.last_seq is not None:
            expected_seq = (self.last_seq + 1) & 0xFFFFFFFF  # Handle wrap
            if seq != expected_seq:
                if seq > expected_seq:
                    gap = seq - expected_seq
                    self.stats.seq_gaps += 1
                    if debug:
                        print(f"[FRAME] ⚠ Sequence gap: {gap} packets ({expected_seq} → {seq})")
                else:
                    self.stats.seq_reorders += 1
                    if debug:
                        print(f"[FRAME] ⚠ Reordered packet: seq={seq} (expected {expected_seq})")

        # Check overflow
        current_total = sum(len(p) for p in self.current_points)
        if current_total + len(points_xyz) > self.max_frame_points:
            self.stats.overflow_frames += 1
            if debug:
                print(f"[FRAME] ⚠ Frame overflow: {current_total}+{len(points_xyz)} > {self.max_frame_points}")
            # Close current frame and start new one
            completed = self._close_current_frame(debug)
            self._start_new_frame(device_ts_ns, seq, debug)
            self.current_points.append(points_xyz.copy())
            self.current_pkt_count += 1
            self.current_frame_end_ts = device_ts_ns
            self.current_seq_last = seq
            self.last_seq = seq
            self.stats.packets_added += 1
            self.stats.points_added += len(points_xyz)
            return completed

        # Add to current frame
        self.current_points.append(points_xyz.copy())
        self.current_pkt_count += 1
        self.current_frame_end_ts = device_ts_ns
        self.current_seq_last = seq
        self.last_seq = seq

        self.stats.packets_added += 1
        self.stats.points_added += len(points_xyz)

        return None

    def _start_new_frame(self, device_ts_ns: int, seq: int, debug: bool):
        """Internal: Start a new frame"""
        self.current_frame_start_ts = device_ts_ns
        self.current_frame_end_ts = device_ts_ns
        self.current_points = []
        self.current_seq_first = seq
        self.current_seq_last = seq
        self.current_pkt_count = 0

        if debug:
            print(f"[FRAME] ▶ New frame started: ts={device_ts_ns}, seq={seq}")

    def _close_current_frame(self, debug: bool) -> Optional[Frame]:
        """Internal: Close current frame and return it"""
        if not self.current_points:
            return None

        # Combine all points
        xyz = np.vstack(self.current_points)  # (N, 3)

        frame = Frame(
            xyz=xyz,
            start_ts_ns=self.current_frame_start_ts,  # type: ignore[arg-type]
            end_ts_ns=self.current_frame_end_ts,  # type: ignore[arg-type]
            seq_first=self.current_seq_first,  # type: ignore[arg-type]
            seq_last=self.current_seq_last,  # type: ignore[arg-type]
            pkt_count=self.current_pkt_count,
            point_count=len(xyz)
        )

        self.stats.frames_built += 1

        if debug:
            print(f"[FRAME] ■ Frame closed: {frame}")

        return frame

    def flush(self, debug: bool = False) -> Optional[Frame]:
        """
        Flush remaining frame (call on shutdown)

        Args:
            debug: Enable debug logging

        Returns:
            Final frame if any points remain, else None
        """
        if self.current_points:
            if debug:
                print("[FRAME] Flushing final frame...")
            return self._close_current_frame(debug)
        return None

    def reset(self):
        """Reset builder state (keeps stats)"""
        self.current_frame_start_ts = None
        self.current_frame_end_ts = None
        self.current_points = []
        self.current_seq_first = None
        self.current_seq_last = None
        self.current_pkt_count = 0
        self.last_seq = None


if __name__ == "__main__":
    # Quick self-test
    print("Frame Builder Test")
    print("=" * 50)

    builder = FrameBuilder(frame_period_s=0.1, max_frame_points=1000)

    # Simulate packets
    base_ts = 1000000000  # 1 second in ns
    seq = 0

    print("\nAdding packets...")
    for i in range(15):
        # 3 packets every 40ms
        ts = base_ts + i * 40_000_000  # 40ms intervals
        points = np.random.rand(50, 3).astype(np.float32)  # 50 points

        frame = builder.add_packet(ts, points, seq, debug=True)
        seq += 1

        if frame:
            print(f"  → {frame}")

    # Flush final frame
    print("\nFlushing...")
    final = builder.flush(debug=True)
    if final:
        print(f"  → {final}")

    print(f"\nStats: {builder.stats}")
