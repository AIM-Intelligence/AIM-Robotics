#!/usr/bin/env python3
"""
Batch API Performance Benchmark

Compare single-packet vs batch processing performance.
"""

import sys
import os
import time
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

def generate_test_packets(num_packets=2000, points_per_packet=96):
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

def test_single_packet_mode(packets):
    """Test original single-packet API."""
    import frame_builder_cpp

    stats = frame_builder_cpp.FrameBuilderStats()
    fb = frame_builder_cpp.FrameBuilder(
        frame_period_s=0.1,  # 100ms frames
        max_frame_points=120000,
        stats=stats
    )

    print(f"\n{'='*60}")
    print("SINGLE-PACKET MODE (Original API)")
    print(f"{'='*60}")

    # Warmup
    for ts_ns, points, seq in packets[:5]:
        fb.add_packet(ts_ns, points, seq)

    # Reset and measure
    fb.reset()
    stats = frame_builder_cpp.FrameBuilderStats()
    fb = frame_builder_cpp.FrameBuilder(
        frame_period_s=0.1,
        max_frame_points=120000,
        stats=stats
    )

    frames_received = 0
    start_time = time.perf_counter()

    for ts_ns, points, seq in packets:
        result = fb.add_packet(ts_ns, points, seq)
        if result is not None:
            frames_received += 1

    # Flush
    result = fb.flush()
    if result is not None:
        frames_received += 1

    end_time = time.perf_counter()

    total_time_s = end_time - start_time
    total_time_ms = total_time_s * 1000
    time_per_packet_us = (total_time_s / len(packets)) * 1_000_000

    print(f"Total time: {total_time_ms:.2f} ms")
    print(f"Time per packet: {time_per_packet_us:.2f} μs")
    print(f"Frames built: {frames_received}")
    print(f"Throughput: {len(packets) / total_time_s:.0f} packets/s")

    return {
        'mode': 'single',
        'time_per_packet_us': time_per_packet_us,
        'total_time_s': total_time_s,
        'frames': frames_received
    }

def test_batch_mode(packets, batch_size=20):
    """Test new batch API."""
    import frame_builder_cpp

    stats = frame_builder_cpp.FrameBuilderStats()
    fb = frame_builder_cpp.FrameBuilder(
        frame_period_s=0.1,  # 100ms frames
        max_frame_points=120000,
        stats=stats
    )

    print(f"\n{'='*60}")
    print(f"BATCH MODE (Batch size: {batch_size})")
    print(f"{'='*60}")

    # Warmup
    batch = packets[:min(batch_size, len(packets))]
    fb.add_packets_batch(
        device_ts_ns_batch=[p[0] for p in batch],
        xyz_batch=[p[1] for p in batch],
        seq_batch=[p[2] for p in batch]
    )

    # Reset and measure
    fb.reset()
    stats = frame_builder_cpp.FrameBuilderStats()
    fb = frame_builder_cpp.FrameBuilder(
        frame_period_s=0.1,
        max_frame_points=120000,
        stats=stats
    )

    frames_received = 0
    start_time = time.perf_counter()

    # Process in batches
    for i in range(0, len(packets), batch_size):
        batch = packets[i:i+batch_size]

        frames = fb.add_packets_batch(
            device_ts_ns_batch=[p[0] for p in batch],
            xyz_batch=[p[1] for p in batch],
            seq_batch=[p[2] for p in batch]
        )

        frames_received += len(frames)

    # Flush
    result = fb.flush()
    if result is not None:
        frames_received += 1

    end_time = time.perf_counter()

    total_time_s = end_time - start_time
    total_time_ms = total_time_s * 1000
    time_per_packet_us = (total_time_s / len(packets)) * 1_000_000
    num_batches = (len(packets) + batch_size - 1) // batch_size

    print(f"Total time: {total_time_ms:.2f} ms")
    print(f"Time per packet: {time_per_packet_us:.2f} μs")
    print(f"Frames built: {frames_received}")
    print(f"Throughput: {len(packets) / total_time_s:.0f} packets/s")
    print(f"Batches processed: {num_batches}")
    print(f"Boundary crossings: {num_batches} (vs {len(packets)} in single mode)")

    return {
        'mode': f'batch_{batch_size}',
        'time_per_packet_us': time_per_packet_us,
        'total_time_s': total_time_s,
        'frames': frames_received,
        'batch_size': batch_size,
        'num_batches': num_batches
    }

def main():
    """Run batch API performance comparison."""
    print("="*60)
    print("Batch API Performance Benchmark")
    print("="*60)

    # Generate test data
    num_packets = 2000
    print(f"\nGenerating {num_packets} test packets...")
    packets = generate_test_packets(num_packets=num_packets, points_per_packet=96)

    # Test single-packet mode
    result_single = test_single_packet_mode(packets)

    # Test batch modes with different batch sizes
    batch_sizes = [10, 20, 50, 100]
    batch_results = []

    for batch_size in batch_sizes:
        result = test_batch_mode(packets, batch_size=batch_size)
        batch_results.append(result)

    # Summary
    print(f"\n{'='*60}")
    print("PERFORMANCE SUMMARY")
    print(f"{'='*60}")

    print(f"\nSingle-packet mode: {result_single['time_per_packet_us']:.2f} μs/packet")

    for result in batch_results:
        speedup = result_single['time_per_packet_us'] / result['time_per_packet_us']
        batch_size = result['batch_size']
        boundary_reduction = len(packets) / result['num_batches']

        print(f"\nBatch size {batch_size:3d}:")
        print(f"  Time per packet:     {result['time_per_packet_us']:.2f} μs")
        print(f"  Speedup:             {speedup:.2f}x")
        print(f"  Boundary crossings:  {result['num_batches']} ({boundary_reduction:.1f}x reduction)")

    # Best batch size
    best = min(batch_results, key=lambda r: r['time_per_packet_us'])
    best_speedup = result_single['time_per_packet_us'] / best['time_per_packet_us']

    print(f"\n{'='*60}")
    print(f"BEST RESULT: Batch size {best['batch_size']}")
    print(f"  Speedup: {best_speedup:.2f}x")
    print(f"  Time: {best['time_per_packet_us']:.2f} μs/packet")
    print(f"{'='*60}\n")

if __name__ == '__main__':
    main()
