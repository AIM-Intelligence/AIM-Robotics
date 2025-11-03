# SLAM RX Performance Benchmark - Python Baseline

**Date:** 2025-11-03 15:42:05
**Platform:** Jetson (ARM64)
**Python:** 3.8.10
**NumPy:** 1.24.4

---

## 1. Protocol Parsing

| Metric | Value | Unit |
|--------|-------|------|
| Average parse time (with CRC) | 24.651889 | μs |
| Throughput | 40564.843541 | packets/sec |
| Average parse time (no CRC) | 23.016368 | μs |
| CRC overhead | 1.635520 | μs |

## 2. Frame Building

| Metric | Value | Unit |
|--------|-------|------|
| add_packet() average | 7.148294 | μs |
| np.vstack (5 arrays, 500 pts) | 136.421000 | μs |
| numpy.copy() overhead | 0.739292 | μs |

## 3. End-to-End Pipeline

| Metric | Value | Unit |
|--------|-------|------|
| Parse average | 36.119752 | μs |
| Build average | 15.162552 | μs |
| Total latency | 51.921164 | μs |
| Max throughput | 19259.968815 | packets/sec |
