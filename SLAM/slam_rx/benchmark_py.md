# SLAM RX Performance Benchmark - Python Baseline

**Date:** 2025-11-03 15:41:53
**Platform:** Jetson (ARM64)
**Python:** 3.8.10
**NumPy:** 1.24.4

---

## 1. Protocol Parsing

| Metric | Value | Unit |
|--------|-------|------|
| Average parse time (with CRC) | 82.439719 | μs |
| Throughput | 12130.075266 | packets/sec |
| Average parse time (no CRC) | 79.689853 | μs |
| CRC overhead | 2.749866 | μs |

## 2. Frame Building

| Metric | Value | Unit |
|--------|-------|------|
| add_packet() average | 7.111888 | μs |
| np.vstack (5 arrays, 500 pts) | 125.252000 | μs |
| numpy.copy() overhead | 0.755036 | μs |

## 3. End-to-End Pipeline

| Metric | Value | Unit |
|--------|-------|------|
| Parse average | 105.742452 | μs |
| Build average | 13.584120 | μs |
| Total latency | 119.898104 | μs |
| Max throughput | 8340.415458 | packets/sec |
