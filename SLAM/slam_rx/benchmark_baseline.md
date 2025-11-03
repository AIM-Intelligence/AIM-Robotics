# SLAM RX Performance Benchmark - Python Baseline

**Date:** 2025-11-03 15:06:03
**Platform:** Jetson (ARM64)
**Python:** 3.8.10
**NumPy:** 1.24.4

---

## 1. Protocol Parsing

| Metric | Value | Unit |
|--------|-------|------|
| Average parse time (with CRC) | 82.837026 | μs |
| Throughput | 12071.896507 | packets/sec |
| Average parse time (no CRC) | 79.457669 | μs |
| CRC overhead | 3.379357 | μs |

## 2. Frame Building

| Metric | Value | Unit |
|--------|-------|------|
| add_packet() average | 7.120572 | μs |
| np.vstack (5 arrays, 500 pts) | 129.541000 | μs |
| numpy.copy() overhead | 0.763677 | μs |

## 3. End-to-End Pipeline

| Metric | Value | Unit |
|--------|-------|------|
| Parse average | 107.059160 | μs |
| Build average | 14.656060 | μs |
| Total latency | 122.309792 | μs |
| Max throughput | 8175.960273 | packets/sec |

---

## Analysis

### Bottlenecks Identified

**1. Protocol Parsing (82.8 μs/packet)**
- `struct.unpack()` in Python loop (105 points × 13 bytes)
- CRC32 validation overhead: 3.4 μs
- NumPy array creation from Python list

**2. Frame Building (129.5 μs for vstack)**
- `np.vstack()` creates new array and copies all data
- Multiple memory allocations per frame
- `numpy.copy()` called for each packet (0.76 μs × 5 = 3.8 μs/frame)

**3. Current Performance at 4Hz Frame Rate**
- 5 packets/frame × 122 μs = **610 μs/frame**
- Frame period = 250 ms (4Hz)
- CPU usage: 610/250,000 = **0.24%**
- Remaining budget: 99.76% (for SLAM processing)

### C++ Optimization Targets

| Component | Current (Python) | Target (C++) | Expected Speedup |
|-----------|------------------|--------------|------------------|
| Protocol Parse | 82.8 μs | 5-10 μs | **8-16x** |
| Frame vstack | 129.5 μs | 10-15 μs | **8-13x** |
| Total Pipeline | 122.3 μs | 15-25 μs | **5-8x** |

### Expected C++ Improvements

**Protocol Parser:**
- Zero-copy parsing (pointer casting instead of struct.unpack)
- SIMD CRC32 (`_mm_crc32_u32` hardware instruction)
- Direct memory mapping to Eigen/NumPy

**Frame Builder:**
- Pre-allocated buffer (no vstack)
- Single memcpy per packet
- Return Eigen::Map view (zero-copy to Python)

**Overall:**
- From 610 μs → **75-125 μs per frame** (5-8x faster)
- More CPU budget for SLAM processing
- Support for higher frame rates (10Hz+)
