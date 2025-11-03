#!/usr/bin/env python3
"""
End-to-End Pipeline Profiling

Measures the actual time spent in each stage of the SLAM pipeline:
- Phase 1: Protocol Parser (Python vs C++)
- Phase 2: Frame Builder (Python vs C++)
- SLAM: KISS-ICP processing

Usage:
    # Profile Python implementation
    SLAMRX_BACKEND=py python3 profile_pipeline.py --duration 30

    # Profile C++ implementation
    SLAMRX_BACKEND=cpp python3 profile_pipeline.py --duration 30
"""

import socket
import argparse
import signal
import sys
import time
import numpy as np
from collections import defaultdict

# Import backend (Python or C++)
from backend import LidarProtocol, ProtocolStats, FrameBuilder, FrameBuilderStats, BACKEND
from slam_pipeline import SlamPipeline, SlamStats


class PipelineProfiler:
    """Profile each stage of the SLAM pipeline"""

    def __init__(self, args):
        self.args = args
        self.running = True

        # Statistics
        self.protocol_stats = ProtocolStats()
        self.frame_stats = FrameBuilderStats()
        self.slam_stats = SlamStats()

        # Components
        self.protocol = LidarProtocol(
            validate_crc=True,
            stats=self.protocol_stats
        )

        self.frame_builder = FrameBuilder(
            frame_period_s=0.1,  # 10Hz
            max_frame_points=120000,
            stats=self.frame_stats
        )

        self.slam_pipeline = SlamPipeline(
            max_range=50.0,
            min_range=0.1,
            voxel_size=0.2,
            self_filter_radius=0.5,
            self_filter_z=0.3,
            min_points_per_frame=100,
            preset='indoor',
            stats=self.slam_stats
        )

        # Timing statistics (in seconds)
        self.timings = {
            'phase1_protocol': [],      # Protocol parsing
            'phase2_frame': [],          # Frame building
            'slam_processing': [],       # SLAM processing
        }

        # Counters
        self.packets_processed = 0
        self.frames_processed = 0
        self.warmup_frames = 0
        self.warmup_needed = 5

        # UDP socket
        self.sock = None

        # Start time
        self.start_time = None

    def setup_socket(self):
        """Setup UDP socket"""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('0.0.0.0', self.args.port))
        self.sock.settimeout(1.0)
        print(f"✓ Listening on UDP port {self.args.port}")

    def signal_handler(self, sig, frame):
        """Handle Ctrl+C"""
        print("\n⚠ Stopping profiler...")
        self.running = False

    def run(self):
        """Main profiling loop"""
        print("\n" + "="*70)
        print("Pipeline Profiling")
        print("="*70)
        print(f"Backend:          {BACKEND}")
        print(f"Duration:         {self.args.duration}s")
        print(f"Port:             {self.args.port}")
        print("="*70 + "\n")

        # Setup
        self.setup_socket()

        # Signal handler
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

        print("Listening for LiDAR packets... (Ctrl+C to stop)\n")

        self.start_time = time.time()

        try:
            while self.running:
                # Check duration
                if time.time() - self.start_time > self.args.duration:
                    print(f"\n⏱ Duration limit reached ({self.args.duration}s)")
                    break

                try:
                    # Receive UDP packet
                    data, addr = self.sock.recvfrom(2048)

                    # ========== PHASE 1: Protocol Parsing ==========
                    t0_protocol = time.perf_counter()
                    packet = self.protocol.parse_datagram(data, debug=False)
                    t1_protocol = time.perf_counter()

                    if packet is None:
                        continue  # Invalid packet

                    self.timings['phase1_protocol'].append(t1_protocol - t0_protocol)
                    self.packets_processed += 1

                    # ========== PHASE 2: Frame Building ==========
                    t0_frame = time.perf_counter()
                    frame = self.frame_builder.add_packet(
                        device_ts_ns=packet['device_ts_ns'],
                        points_xyz=packet['xyz'],
                        seq=packet['seq'],
                        debug=False
                    )
                    t1_frame = time.perf_counter()

                    self.timings['phase2_frame'].append(t1_frame - t0_frame)

                    # ========== SLAM Processing ==========
                    if frame is not None:
                        # Skip warmup frames
                        if self.warmup_frames < self.warmup_needed:
                            self.warmup_frames += 1
                            if self.warmup_frames == 1:
                                print(f"⏳ [WARMUP] Discarding first {self.warmup_needed} frames...")
                            continue

                        t0_slam = time.perf_counter()
                        result = self.slam_pipeline.register_frame(frame, debug=False)
                        t1_slam = time.perf_counter()

                        if result is not None:
                            self.timings['slam_processing'].append(t1_slam - t0_slam)
                            self.frames_processed += 1

                    # Periodic status
                    if self.packets_processed % 1000 == 0:
                        elapsed = time.time() - self.start_time
                        pps = self.packets_processed / elapsed
                        fps = self.frames_processed / elapsed if self.frames_processed > 0 else 0
                        print(f"[{elapsed:.1f}s] Packets: {self.packets_processed} ({pps:.0f} pps), "
                              f"Frames: {self.frames_processed} ({fps:.1f} fps)")

                except socket.timeout:
                    continue  # Normal timeout

                except Exception as e:
                    print(f"❌ Error: {e}")
                    if self.args.debug:
                        import traceback
                        traceback.print_exc()

        except KeyboardInterrupt:
            print("\n⚠ Interrupted by user")

        finally:
            self.shutdown()

    def shutdown(self):
        """Cleanup and report results"""
        print("\n" + "="*70)
        print("PROFILING RESULTS")
        print("="*70)

        # Close socket
        if self.sock:
            self.sock.close()

        # Check if we have data
        if self.packets_processed == 0:
            print("❌ No packets received!")
            return

        # Calculate statistics
        elapsed = time.time() - self.start_time

        print(f"\nBackend: {BACKEND}")
        print(f"Duration: {elapsed:.1f}s")
        print(f"Packets processed: {self.packets_processed}")
        print(f"Frames processed: {self.frames_processed}")

        # Average packets per frame
        if self.frames_processed > 0:
            packets_per_frame = self.packets_processed / self.frames_processed
            print(f"Packets per frame: {packets_per_frame:.1f}")

        print("\n" + "="*70)
        print("TIME PER PACKET (microseconds)")
        print("="*70)

        # Phase 1: Protocol parsing
        if self.timings['phase1_protocol']:
            times_us = np.array(self.timings['phase1_protocol']) * 1e6
            mean_us = np.mean(times_us)
            std_us = np.std(times_us)
            median_us = np.median(times_us)
            p95_us = np.percentile(times_us, 95)

            print(f"\nPhase 1: Protocol Parser ({BACKEND})")
            print(f"  Mean:    {mean_us:.2f} μs/packet")
            print(f"  Median:  {median_us:.2f} μs/packet")
            print(f"  Std:     {std_us:.2f} μs")
            print(f"  95th %:  {p95_us:.2f} μs")
            print(f"  Samples: {len(times_us)}")

        # Phase 2: Frame building
        if self.timings['phase2_frame']:
            times_us = np.array(self.timings['phase2_frame']) * 1e6
            mean_us = np.mean(times_us)
            std_us = np.std(times_us)
            median_us = np.median(times_us)
            p95_us = np.percentile(times_us, 95)

            print(f"\nPhase 2: Frame Builder ({BACKEND})")
            print(f"  Mean:    {mean_us:.2f} μs/packet")
            print(f"  Median:  {median_us:.2f} μs/packet")
            print(f"  Std:     {std_us:.2f} μs")
            print(f"  95th %:  {p95_us:.2f} μs")
            print(f"  Samples: {len(times_us)}")

        print("\n" + "="*70)
        print("TIME PER FRAME (milliseconds)")
        print("="*70)

        # SLAM processing
        if self.timings['slam_processing']:
            times_ms = np.array(self.timings['slam_processing']) * 1e3
            mean_ms = np.mean(times_ms)
            std_ms = np.std(times_ms)
            median_ms = np.median(times_ms)
            p95_ms = np.percentile(times_ms, 95)

            print(f"\nSLAM: KISS-ICP (C++ via pybind11)")
            print(f"  Mean:    {mean_ms:.2f} ms/frame")
            print(f"  Median:  {median_ms:.2f} ms/frame")
            print(f"  Std:     {std_ms:.2f} ms")
            print(f"  95th %:  {p95_ms:.2f} ms")
            print(f"  Samples: {len(times_ms)}")

        # Calculate total time per frame
        print("\n" + "="*70)
        print("TOTAL TIME PER FRAME")
        print("="*70)

        if self.frames_processed > 0 and self.timings['slam_processing']:
            # Average packets per frame
            packets_per_frame = self.packets_processed / self.frames_processed

            # Phase 1 + Phase 2 (per packet) * packets_per_frame
            phase1_per_packet_us = np.mean(self.timings['phase1_protocol']) * 1e6
            phase2_per_packet_us = np.mean(self.timings['phase2_frame']) * 1e6

            phase1_per_frame_ms = (phase1_per_packet_us * packets_per_frame) / 1000.0
            phase2_per_frame_ms = (phase2_per_packet_us * packets_per_frame) / 1000.0

            # SLAM (per frame)
            slam_per_frame_ms = np.mean(self.timings['slam_processing']) * 1e3

            # Total
            total_ms = phase1_per_frame_ms + phase2_per_frame_ms + slam_per_frame_ms

            print(f"\nPer-frame breakdown (based on {packets_per_frame:.1f} packets/frame):")
            print(f"  Phase 1 (Protocol):  {phase1_per_frame_ms:.2f} ms  ({phase1_per_frame_ms/total_ms*100:.1f}%)")
            print(f"  Phase 2 (Frame):     {phase2_per_frame_ms:.2f} ms  ({phase2_per_frame_ms/total_ms*100:.1f}%)")
            print(f"  SLAM (KISS-ICP):     {slam_per_frame_ms:.2f} ms  ({slam_per_frame_ms/total_ms*100:.1f}%)")
            print(f"  {'─'*50}")
            print(f"  TOTAL:               {total_ms:.2f} ms/frame")
            print(f"\n  Theoretical max FPS: {1000.0/total_ms:.1f} fps")
            print(f"  Actual FPS:          {self.frames_processed/elapsed:.1f} fps")

        print("\n" + "="*70 + "\n")


def main():
    parser = argparse.ArgumentParser(description='Profile SLAM pipeline stages')
    parser.add_argument('--port', type=int, default=8889,
                        help='UDP port to listen on')
    parser.add_argument('--duration', type=int, default=30,
                        help='Profiling duration in seconds')
    parser.add_argument('--debug', action='store_true',
                        help='Enable debug output')

    args = parser.parse_args()

    profiler = PipelineProfiler(args)
    profiler.run()


if __name__ == '__main__':
    main()
