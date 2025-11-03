#!/usr/bin/env python3
"""
Performance Benchmark Suite - Pre C++ Optimization

Measures current Python implementation performance:
- Protocol parsing speed
- Frame building speed (especially np.vstack)
- End-to-end pipeline latency
- Memory usage

Usage:
    python3 benchmark.py [--save results.md]
"""

import time
import struct
import numpy as np
import argparse
from pathlib import Path
from datetime import datetime
import sys
import gc

# Import modules to benchmark
from backend import LidarProtocol, ProtocolStats  # Auto-select Python/C++ backend
from frame_builder import FrameBuilder, FrameBuilderStats


class BenchmarkResults:
    """Store and format benchmark results"""

    def __init__(self):
        self.timestamp = datetime.now()
        self.results = {}

    def add(self, category: str, metric: str, value, unit: str):
        """Add a benchmark result"""
        if category not in self.results:
            self.results[category] = []
        self.results[category].append({
            'metric': metric,
            'value': value,
            'unit': unit
        })

    def to_markdown(self) -> str:
        """Format results as markdown"""
        lines = [
            "# SLAM RX Performance Benchmark - Python Baseline",
            "",
            f"**Date:** {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Platform:** Jetson (ARM64)",
            f"**Python:** {sys.version.split()[0]}",
            f"**NumPy:** {np.__version__}",
            "",
            "---",
            ""
        ]

        for category, metrics in self.results.items():
            lines.append(f"## {category}")
            lines.append("")
            lines.append("| Metric | Value | Unit |")
            lines.append("|--------|-------|------|")

            for m in metrics:
                lines.append(f"| {m['metric']} | {m['value']:.6f} | {m['unit']} |")

            lines.append("")

        return "\n".join(lines)


def create_test_packet(point_count: int = 100, seq: int = 0) -> bytes:
    """
    Create a valid test packet

    Args:
        point_count: Number of points (1-105)
        seq: Sequence number

    Returns:
        Raw packet bytes
    """
    # Header
    magic = 0x4C495652
    version = 1
    device_ts_ns = int(time.time() * 1e9)
    flags = 0
    sensor_id = 0

    # Pack header (without CRC)
    header_no_crc = struct.pack('<IBQIHHH',
                                magic, version, device_ts_ns, seq,
                                point_count, flags, sensor_id)

    # Generate random points
    points_bytes = b''
    for i in range(point_count):
        x = np.random.uniform(-10, 10)
        y = np.random.uniform(-10, 10)
        z = np.random.uniform(-2, 2)
        intensity = np.random.randint(0, 256)
        points_bytes += struct.pack('<fffB', x, y, z, intensity)

    # Calculate CRC
    crc_data = header_no_crc + points_bytes
    import zlib
    crc32 = zlib.crc32(crc_data) & 0xFFFFFFFF

    # Final packet
    packet = header_no_crc + struct.pack('<I', crc32) + points_bytes

    return packet


def benchmark_protocol_parsing(results: BenchmarkResults, n_packets: int = 10000):
    """Benchmark protocol parsing performance"""
    print(f"\n{'='*70}")
    print("BENCHMARK 1: Protocol Parsing")
    print(f"{'='*70}")

    # Create test packets (various sizes)
    packet_sizes = [50, 75, 100, 105]  # points per packet
    test_packets = []

    for size in packet_sizes:
        for i in range(n_packets // len(packet_sizes)):
            test_packets.append(create_test_packet(size, i))

    print(f"Created {len(test_packets)} test packets")

    # Warmup
    parser = LidarProtocol(validate_crc=True)
    for pkt in test_packets[:100]:
        parser.parse_datagram(pkt)

    # Benchmark: Full parsing (with CRC)
    gc.collect()
    parser = LidarProtocol(validate_crc=True)
    start = time.perf_counter()

    for pkt in test_packets:
        result = parser.parse_datagram(pkt)
        assert result is not None

    elapsed = time.perf_counter() - start

    avg_time = elapsed / len(test_packets)
    throughput = len(test_packets) / elapsed

    print(f"  Full Parse (with CRC):  {avg_time*1e6:.2f} μs/packet")
    print(f"  Throughput:             {throughput:.0f} packets/sec")

    results.add("1. Protocol Parsing", "Average parse time (with CRC)", avg_time * 1e6, "μs")
    results.add("1. Protocol Parsing", "Throughput", throughput, "packets/sec")

    # Benchmark: Parsing without CRC
    gc.collect()
    parser = LidarProtocol(validate_crc=False)
    start = time.perf_counter()

    for pkt in test_packets:
        result = parser.parse_datagram(pkt)

    elapsed = time.perf_counter() - start
    avg_time_no_crc = elapsed / len(test_packets)

    print(f"  Parse (no CRC):         {avg_time_no_crc*1e6:.2f} μs/packet")
    print(f"  CRC overhead:           {(avg_time - avg_time_no_crc)*1e6:.2f} μs/packet")

    results.add("1. Protocol Parsing", "Average parse time (no CRC)", avg_time_no_crc * 1e6, "μs")
    results.add("1. Protocol Parsing", "CRC overhead", (avg_time - avg_time_no_crc) * 1e6, "μs")


def benchmark_frame_building(results: BenchmarkResults):
    """Benchmark frame building performance (especially vstack)"""
    print(f"\n{'='*70}")
    print("BENCHMARK 2: Frame Building")
    print(f"{'='*70}")

    # Simulate realistic workload: 4Hz frames, 20Hz LiDAR = 5 packets/frame
    frame_rate = 4  # Hz
    frame_period_s = 1.0 / frame_rate
    packets_per_frame = 5
    n_frames = 100
    points_per_packet = 100

    builder = FrameBuilder(frame_period_s=frame_period_s, max_frame_points=120000)

    # Create test data
    base_ts = int(time.time() * 1e9)
    packet_interval_ns = int((frame_period_s / packets_per_frame) * 1e9)

    # Warmup
    for i in range(10):
        ts = base_ts + i * packet_interval_ns
        xyz = np.random.rand(points_per_packet, 3).astype(np.float32)
        builder.add_packet(ts, xyz, i)

    # Benchmark: add_packet (without vstack)
    gc.collect()
    add_times = []

    base_ts = int(time.time() * 1e9)
    seq = 0

    for frame_idx in range(n_frames):
        for pkt_idx in range(packets_per_frame):
            ts = base_ts + (frame_idx * packets_per_frame + pkt_idx) * packet_interval_ns
            xyz = np.random.rand(points_per_packet, 3).astype(np.float32)

            start = time.perf_counter()
            result = builder.add_packet(ts, xyz, seq)
            elapsed = time.perf_counter() - start

            add_times.append(elapsed)
            seq += 1

    avg_add_time = np.mean(add_times)
    print(f"  add_packet():           {avg_add_time*1e6:.2f} μs/call")

    results.add("2. Frame Building", "add_packet() average", avg_add_time * 1e6, "μs")

    # Benchmark: vstack specifically
    print("\n  Testing np.vstack overhead:")

    vstack_times = []
    for n_arrays in [5, 10, 20]:
        # Create list of arrays
        arrays = [np.random.rand(points_per_packet, 3).astype(np.float32)
                  for _ in range(n_arrays)]

        gc.collect()
        start = time.perf_counter()
        combined = np.vstack(arrays)
        elapsed = time.perf_counter() - start

        total_points = n_arrays * points_per_packet
        print(f"    {n_arrays:2d} arrays ({total_points:4d} pts): {elapsed*1e6:6.2f} μs")

        vstack_times.append(elapsed)

        if n_arrays == 5:  # Most common case
            results.add("2. Frame Building", "np.vstack (5 arrays, 500 pts)", elapsed * 1e6, "μs")

    # Benchmark: Memory copy overhead
    print("\n  Memory copy overhead:")

    xyz = np.random.rand(points_per_packet, 3).astype(np.float32)

    gc.collect()
    start = time.perf_counter()
    for _ in range(1000):
        copy = xyz.copy()
    elapsed = time.perf_counter() - start

    avg_copy = elapsed / 1000
    print(f"    numpy.copy():           {avg_copy*1e6:.2f} μs/array ({xyz.nbytes} bytes)")

    results.add("2. Frame Building", "numpy.copy() overhead", avg_copy * 1e6, "μs")


def benchmark_end_to_end(results: BenchmarkResults):
    """Benchmark complete pipeline: parse + build"""
    print(f"\n{'='*70}")
    print("BENCHMARK 3: End-to-End Pipeline")
    print(f"{'='*70}")

    # Setup
    frame_rate = 4  # Hz
    frame_period_s = 1.0 / frame_rate
    n_frames = 50
    packets_per_frame = 5

    parser = LidarProtocol(validate_crc=True)
    builder = FrameBuilder(frame_period_s=frame_period_s)

    # Create test packets
    base_ts = int(time.time() * 1e9)
    packet_interval_ns = int((frame_period_s / packets_per_frame) * 1e9)

    test_packets = []
    for i in range(n_frames * packets_per_frame):
        ts = base_ts + i * packet_interval_ns
        pkt = create_test_packet(100, i)
        test_packets.append(pkt)

    # Warmup
    for pkt in test_packets[:20]:
        parsed = parser.parse_datagram(pkt)
        if parsed:
            builder.add_packet(parsed['device_ts_ns'], parsed['xyz'], parsed['seq'])

    # Benchmark: Full pipeline
    gc.collect()
    parser = LidarProtocol(validate_crc=True)
    builder = FrameBuilder(frame_period_s=frame_period_s)

    parse_times = []
    build_times = []
    total_times = []

    for pkt in test_packets:
        start_total = time.perf_counter()

        # Parse
        start_parse = time.perf_counter()
        parsed = parser.parse_datagram(pkt)
        parse_time = time.perf_counter() - start_parse

        # Build
        start_build = time.perf_counter()
        frame = builder.add_packet(parsed['device_ts_ns'], parsed['xyz'], parsed['seq'])
        build_time = time.perf_counter() - start_build

        total_time = time.perf_counter() - start_total

        parse_times.append(parse_time)
        build_times.append(build_time)
        total_times.append(total_time)

    avg_parse = np.mean(parse_times)
    avg_build = np.mean(build_times)
    avg_total = np.mean(total_times)

    print(f"  Parse:                  {avg_parse*1e6:.2f} μs")
    print(f"  Build:                  {avg_build*1e6:.2f} μs")
    print(f"  Total:                  {avg_total*1e6:.2f} μs")
    print(f"  Max throughput:         {1.0/avg_total:.0f} packets/sec")

    results.add("3. End-to-End Pipeline", "Parse average", avg_parse * 1e6, "μs")
    results.add("3. End-to-End Pipeline", "Build average", avg_build * 1e6, "μs")
    results.add("3. End-to-End Pipeline", "Total latency", avg_total * 1e6, "μs")
    results.add("3. End-to-End Pipeline", "Max throughput", 1.0 / avg_total, "packets/sec")


def main():
    parser = argparse.ArgumentParser(description="SLAM RX Performance Benchmark")
    parser.add_argument('--save', type=str, default='benchmark_baseline.md',
                       help='Save results to markdown file')
    parser.add_argument('--packets', type=int, default=10000,
                       help='Number of packets for protocol benchmark')
    args = parser.parse_args()

    print("\n" + "="*70)
    print("SLAM RX Performance Benchmark - Python Baseline")
    print("="*70)
    print(f"Platform: Jetson ARM64")
    print(f"Python: {sys.version.split()[0]}")
    print(f"NumPy: {np.__version__}")

    results = BenchmarkResults()

    # Run benchmarks
    benchmark_protocol_parsing(results, n_packets=args.packets)
    benchmark_frame_building(results)
    benchmark_end_to_end(results)

    # Summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    print("\nBottlenecks identified:")
    print("  1. Protocol parsing:     struct.unpack() + Python loops")
    print("  2. Frame building:       np.vstack() memory copies")
    print("  3. Memory overhead:      Multiple .copy() calls")

    # Save results
    if args.save:
        md = results.to_markdown()
        output_path = Path(__file__).parent / args.save
        output_path.write_text(md)
        print(f"\n✓ Results saved to: {output_path}")
        print(f"  Run: cat {output_path}")

    print()


if __name__ == "__main__":
    main()
