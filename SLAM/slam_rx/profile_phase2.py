#!/usr/bin/env python3
"""
Phase 2 Frame Builder Profiling Benchmark

This script runs controlled experiments to identify the root cause of
Phase 2 C++ Frame Builder performance issues.

Expected output:
- Timing comparison (Python vs C++)
- C++ internal profiling statistics
- pybind11 boundary overhead analysis
"""

import sys
import os
import time
import numpy as np
from pathlib import Path

# Add slam_rx to path
sys.path.insert(0, str(Path(__file__).parent))

def generate_test_packets(num_packets=1000, points_per_packet=96):
    """Generate synthetic LiDAR packets for testing."""
    packets = []
    base_ts = 1000000000  # 1 second in nanoseconds

    for i in range(num_packets):
        # Generate random point cloud
        points = np.random.randn(points_per_packet, 3).astype(np.float32)

        # Timestamp: 10ms per packet
        ts_ns = base_ts + i * 10_000_000

        # Sequence number
        seq = i

        packets.append((ts_ns, points, seq))

    return packets

def run_benchmark(backend_name, packets, use_batch=False, batch_size=20):
    """Run benchmark for a specific backend."""
    mode_str = f"{backend_name} (Batch {batch_size})" if use_batch else backend_name
    print(f"\n{'='*60}")
    print(f"Testing backend: {mode_str}")
    print(f"{'='*60}")

    # Set backend
    os.environ['SLAMRX_BACKEND'] = backend_name

    # Import fresh backend
    import importlib
    import backend as backend_module
    importlib.reload(backend_module)

    # Get frame builder from backend
    FrameBuilder = backend_module.FrameBuilder
    FrameBuilderStats = backend_module.FrameBuilderStats

    # Create statistics object
    stats = FrameBuilderStats()
    fb = FrameBuilder(
        frame_period_s=0.1,  # 100ms frames
        max_frame_points=120000,
        stats=stats
    )

    # Warm-up (5 packets)
    print("Warm-up...")
    for ts_ns, points, seq in packets[:5]:
        fb.add_packet(ts_ns, points, seq)

    # Reset for actual benchmark
    fb.reset()
    stats = FrameBuilderStats()
    fb = FrameBuilder(
        frame_period_s=0.1,
        max_frame_points=120000,
        stats=stats
    )

    # Actual benchmark
    print(f"Processing {len(packets)} packets...")
    frames_received = 0

    start_time = time.perf_counter()

    if use_batch and backend_name == 'cpp':
        # Batch mode (only for C++ backend)
        for i in range(0, len(packets), batch_size):
            batch = packets[i:i+batch_size]

            frames = fb.add_packets_batch(
                device_ts_ns_batch=[p[0] for p in batch],
                xyz_batch=[p[1] for p in batch],
                seq_batch=[p[2] for p in batch]
            )

            frames_received += len(frames)
    else:
        # Single-packet mode
        for ts_ns, points, seq in packets:
            result = fb.add_packet(ts_ns, points, seq)
            if result is not None:
                frames_received += 1

    # Flush remaining frame
    result = fb.flush()
    if result is not None:
        frames_received += 1

    end_time = time.perf_counter()

    # Results
    total_time_s = end_time - start_time
    total_time_ms = total_time_s * 1000
    time_per_packet_us = (total_time_s / len(packets)) * 1_000_000

    print(f"\n{'='*60}")
    print(f"Results for {backend_name}")
    print(f"{'='*60}")
    print(f"Total time: {total_time_ms:.2f} ms")
    print(f"Time per packet: {time_per_packet_us:.2f} μs")
    print(f"Packets processed: {len(packets)}")
    print(f"Frames built: {frames_received}")
    print(f"Throughput: {len(packets) / total_time_s:.0f} packets/s")

    print(f"\nStatistics:")
    print(f"  frames_built: {stats.frames_built}")
    print(f"  packets_added: {stats.packets_added}")
    print(f"  points_added: {stats.points_added}")
    print(f"  late_packets: {stats.late_packets}")
    print(f"  seq_gaps: {stats.seq_gaps}")
    print(f"  seq_reorders: {stats.seq_reorders}")
    print(f"  overflow_frames: {stats.overflow_frames}")

    # Print C++ profiling stats if available
    if backend_name == 'cpp':
        try:
            import frame_builder_cpp
            print(f"\n{'='*60}")
            print("C++ Internal Profiling Statistics")
            print(f"{'='*60}")
            frame_builder_cpp.print_cpp_profiling_stats()

            print(f"\n{'='*60}")
            print("Pybind11 Boundary Profiling Statistics")
            print(f"{'='*60}")
            frame_builder_cpp.print_pybind_profiling_stats()
        except Exception as e:
            print(f"Could not get C++ profiling stats: {e}")

    result = {
        'backend': backend_name,
        'total_time_s': total_time_s,
        'time_per_packet_us': time_per_packet_us,
        'packets': len(packets),
        'frames': frames_received,
        'throughput': len(packets) / total_time_s,
        'use_batch': use_batch
    }

    if use_batch:
        result['batch_size'] = batch_size

    return result

def main():
    """Run profiling experiments."""
    print("="*60)
    print("Phase 2 Frame Builder Profiling Benchmark")
    print("="*60)

    # Generate test data
    print("\nGenerating test packets...")
    num_packets = 2000
    packets = generate_test_packets(num_packets=num_packets, points_per_packet=96)
    print(f"Generated {num_packets} packets with 96 points each")

    # Run benchmarks
    results = []

    # Python baseline
    result_py = run_benchmark('py', packets)
    results.append(result_py)

    # C++ single-packet mode
    result_cpp_single = run_benchmark('cpp', packets, use_batch=False)
    results.append(result_cpp_single)

    # C++ batch modes
    batch_sizes = [10, 20, 50]
    batch_results = []
    for batch_size in batch_sizes:
        result = run_benchmark('cpp', packets, use_batch=True, batch_size=batch_size)
        batch_results.append(result)

    # Comparison
    print(f"\n{'='*60}")
    print("PERFORMANCE COMPARISON")
    print(f"{'='*60}")
    print(f"\nPython (baseline):      {result_py['time_per_packet_us']:.2f} μs/packet")
    print(f"C++ (single-packet):    {result_cpp_single['time_per_packet_us']:.2f} μs/packet")

    speedup_single = result_py['time_per_packet_us'] / result_cpp_single['time_per_packet_us']
    print(f"  → Speedup: {speedup_single:.2f}x")

    if speedup_single < 1.0:
        print(f"  ⚠️  WARNING: C++ is SLOWER than Python by {1/speedup_single:.2f}x")
    else:
        print(f"  ✅ C++ is faster than Python")

    print(f"\nC++ Batch Modes:")
    best_result = result_cpp_single
    best_speedup = speedup_single

    for result in batch_results:
        batch_size = result.get('batch_size', 20)
        speedup_vs_py = result_py['time_per_packet_us'] / result['time_per_packet_us']
        speedup_vs_single = result_cpp_single['time_per_packet_us'] / result['time_per_packet_us']

        print(f"\n  Batch size {batch_size}:  {result['time_per_packet_us']:.2f} μs/packet")
        print(f"    → vs Python:     {speedup_vs_py:.2f}x faster")
        print(f"    → vs C++ single: {speedup_vs_single:.2f}x faster")

        if speedup_vs_py > best_speedup:
            best_speedup = speedup_vs_py
            best_result = result

    print(f"\n{'='*60}")
    print(f"BEST RESULT: Batch size {best_result.get('batch_size', 'N/A')}")
    print(f"  Total speedup vs Python: {best_speedup:.2f}x")
    print(f"  Time per packet: {best_result['time_per_packet_us']:.2f} μs")
    print(f"{'='*60}")

    print(f"\n{'='*60}")
    print("Profiling Analysis:")
    print(f"{'='*60}")
    print("Check the C++ profiling statistics above to identify:")
    print("1. C++ internal timing (memcpy, add_to_frame, close_frame)")
    print("2. pybind11 boundary overhead (validation, pointer extraction, dict creation)")
    print("3. Batch API effectiveness (boundary crossing reduction)")
    print(f"{'='*60}\n")

if __name__ == '__main__':
    main()
