# LiDAR Stream  Protocol Specification

**Version:** 1
**Date:** 2025-11-02
**Status:** Production

---

## Overview

This document specifies the UDP-based protocol for streaming LiDAR point cloud data from the Livox Mid-360 sensor to SLAM/visualization consumers.

**Design Goals:**
- Enable reliable frame reconstruction at receiver
- Provide device-based timestamps for accurate temporal registration
- Detect packet loss and reordering
- Support future protocol extensions
- Maintain MTU safety for network reliability

---

## Protocol Format

### Packet Structure

Each UDP datagram contains:

```
┌─────────────────────────────────┐
│  PacketHeader (27 bytes)        │
├─────────────────────────────────┤
│  Point3D[0] (13 bytes)          │
│  Point3D[1] (13 bytes)          │
│  ...                            │
│  Point3D[N-1] (13 bytes)        │
└─────────────────────────────────┘
```

**Maximum Payload:** 1400 bytes (safe for standard 1500 MTU)
**Maximum Points per Packet:** `floor((1400 - 27) / 13) = 105 points`

---

## Data Structures

### PacketHeader (27 bytes)

All multi-byte fields are **LITTLE-ENDIAN**.

| Offset | Type     | Name              | Description                                      |
|--------|----------|-------------------|--------------------------------------------------|
| 0      | uint32   | magic             | Protocol magic number: `0x4C495652` ("LIVR")    |
| 4      | uint8    | version           | Protocol version (current: 1)                    |
| 5      | uint64   | device_timestamp  | Device monotonic time in nanoseconds             |
| 13     | uint32   | seq               | Sequence number (wraps at 2^32)                  |
| 17     | uint16   | point_count       | Number of points in this packet (1-105)          |
| 19     | uint16   | flags             | Reserved for future use (set to 0)               |
| 21     | uint16   | sensor_id         | Sensor identifier (0 = primary LiDAR)            |
| 23     | uint32   | crc32             | CRC32 checksum (optional, 0 if disabled)         |

**Total:** 27 bytes

#### Field Details

**magic (4 bytes)**
- Value: `0x4C495652` (ASCII "LIVR" in little-endian)
- Used for packet validation and protocol identification
- Receivers MUST reject packets with incorrect magic

**version (1 byte)**
- Current version: `1`
- Receivers SHOULD handle version mismatches gracefully
- Future versions MAY extend the header (check `flags`)

**device_timestamp (8 bytes)**
- Unit: Nanoseconds (uint64_t, little-endian)
- **Source**: Livox Mid-360 hardware timestamp (extracted from LivoxLidarEthernetPacket)
- **Clock domain**: Device monotonic time (prefer Livox `time_type == 0`)
- **Time types** (from Livox SDK):
  - `0`: Device monotonic (preferred - hardware timestamp)
  - `1`: PTP synchronized time
  - `2`: GPS synchronized time
  - `3`: PPS synchronized time
- **Fallback**: Host monotonic time (`CLOCK_MONOTONIC`) if device timestamp unavailable
- **Validation**: Transmitter performs sanity check (Δt < 1 second between packets)
- **Critical for frame reconstruction**
- Receivers MUST use this for temporal windowing, NOT packet arrival time

**seq (4 bytes)**
- Monotonically increasing sequence number
- Wraps around at 2^32 (4,294,967,296)
- Incremented for EACH packet (not per frame)
- Used to detect packet loss and reordering

**point_count (2 bytes)**
- Number of Point3D structures following the header
- Valid range: 1-105 (based on MTU limit)
- Receivers MUST validate against packet size

**flags (2 bytes)**
- Reserved for future extensions
- Current version: MUST be 0
- Possible future uses:
  - Bit 0: Compression enabled
  - Bit 1: Deskew timestamps included
  - Bit 2: Multi-sensor mode
  - Bits 3-15: Reserved

**sensor_id (2 bytes)**
- Identifies the source sensor in multi-sensor setups
- Default: 0 (primary LiDAR)
- Future: Support multiple LiDAR units

**crc32 (4 bytes)**
- **Algorithm**: IEEE 802.3 CRC32 (polynomial: 0xEDB88320 reflected)
- **Calculation range**: header[0..22] + payload (23 header bytes + all point data)
  - **Excludes**: CRC field itself (bytes 23-26)
  - **Initial value**: 0xFFFFFFFF
  - **Final XOR**: 0xFFFFFFFF
- **Enabled**: Set via `--crc` flag or `LIDAR_CRC32=1` environment variable
- **Disabled**: Field set to `0x00000000`
- **Self-test**: Transmitter validates implementation with IEEE 802.3 test vectors on startup
- Receivers SHOULD validate if non-zero, discard packet on mismatch

---

### Point3D (13 bytes)

Each point contains spatial coordinates and intensity.

| Offset | Type     | Name      | Description                                    |
|--------|----------|-----------|------------------------------------------------|
| 0      | float    | x         | X coordinate in meters (little-endian IEEE 754)|
| 4      | float    | y         | Y coordinate in meters (little-endian IEEE 754)|
| 8      | float    | z         | Z coordinate in meters (little-endian IEEE 754)|
| 12     | uint8    | intensity | Reflectivity (0-255)                           |

**Total:** 13 bytes (packed, no padding)

#### Coordinate Frame

**Sensor Frame (before mount correction):**
- **X:** Forward (sensor front)
- **Y:** Left (sensor left side)
- **Z:** Up (sensor top)

**Units:** Meters (converted from Livox native millimeters)

**Mount Correction:**
- If sensor is mounted upside-down or tilted, correction MUST be applied consistently
- **Policy:** Apply mount correction ONCE in the pipeline (either at transmitter or receiver, not both)
- Default: Transmitter sends raw sensor frame, receiver applies mount correction

---

## Protocol Semantics

### Packet Transmission

**Ordering:**
- Packets are sent in sequence order
- UDP does not guarantee order; receivers MUST handle reordering

**Loss Handling:**
- No retransmission (UDP best-effort)
- Receivers detect gaps via `seq` field
- Lost packets → missing points in that time window

**Rate:**
- Dependent on LiDAR callback frequency (~100-200 Hz)
- Typical throughput: 10-30 Mbit/s

### Frame Reconstruction (Receiver Side)

Receivers MUST reconstruct frames using **device_timestamp**, not packet arrival time.

**Recommended Algorithm:**

1. **Fixed Time Window:**
   - Define window size (e.g., `FRAME_DT = 0.10 seconds = 100,000,000 ns`)
   - Maintain current frame start timestamp

2. **Packet Processing:**
   ```
   For each received packet:
     - Validate magic, version, CRC
     - Check seq for gaps/reorder
     - If (device_timestamp - frame_start) > FRAME_DT:
         → Emit current frame to SLAM
         → Start new frame
     - Accumulate points into current frame buffer
   ```

3. **Sequence Validation:**
   ```
   expected_seq = last_seq + 1 (mod 2^32)
   if received_seq != expected_seq:
     gap = received_seq - expected_seq
     if gap > 0:
       log "Packet loss: %d packets", gap
       increment loss counter
     else:
       log "Reordered packet: seq=%u", received_seq
   ```

4. **Per-Point Timestamps:**
   - Minimum: Linearly interpolate from `0` to `FRAME_DT`
   - Optimal: Use per-point offsets if available (future extension)

---

## Distance Filtering

**Transmitter-Side (Recommended):**
- Min range: 0.1 m (configurable)
- Max range: 20.0 m indoor / 120.0 m outdoor (configurable)
- Filter out (0,0,0) points
- Filter points outside range to reduce bandwidth

**Receiver-Side (Optional):**
- Additional filtering for SLAM quality
- Example: Remove ground plane, ceiling, robot body

---

## Endianness

**All multi-byte fields are LITTLE-ENDIAN:**
- uint16, uint32, uint64: Little-endian byte order
- float: IEEE 754 single precision, little-endian

**Rationale:**
- ARM (Jetson) and x86 (Mac/PC) are natively little-endian
- Explicit specification ensures cross-platform compatibility

**Conversion (if needed):**
```c
// Host to little-endian (no-op on ARM/x86)
uint32_t le_value = htole32(host_value);

// Little-endian to host
uint32_t host_value = le32toh(le_value);
```

---

## Error Handling

### Transmitter

**Buffer Full (EAGAIN/EWOULDBLOCK):**
- Drop packet
- Increment `stats_dropped_packets`
- Continue with next packet (do NOT block)

**Socket Errors:**
- Log error
- Attempt to continue (graceful degradation)

### Receiver

**Invalid Magic:**
- Discard packet silently
- Increment `invalid_packets` counter

**Version Mismatch:**
- Log warning
- Attempt to parse if backward compatible
- Discard if incompatible

**CRC Failure:**
- Discard packet
- Increment `crc_errors` counter

**Point Count Validation:**
- Expected size: `27 + point_count * 13`
- If mismatch → discard packet

**Sequence Gaps:**
- Log gap size
- Continue processing (missing points in frame)
- If gap > threshold (e.g., 100) → skip frame update

---

## Extensions (Future Versions)

### Planned Features

**Version 2:**
- Per-point timestamps (deskew support)
- Compression (zstd/lz4)
- Multi-sensor aggregation

**Version 3:**
- IMU data embedding
- Coordinate frame metadata in header
- Adaptive quality/rate control

**Backward Compatibility:**
- Version 1 receivers MAY ignore unknown `flags` bits
- Version 1 receivers MUST reject `version > 1` if critical changes

---

## Performance Characteristics

### Network Bandwidth

**Typical Configuration:**
- Points per second: ~100,000
- Points per packet: ~100
- Packets per second: ~1,000
- Bytes per packet: ~1,327 (27 header + 1,300 payload)
- **Total bandwidth: ~10-15 Mbit/s**

### Frame Rate

**SLAM Processing:**
- Frame window: 0.10 s
- Frame rate: 10 Hz
- Points per frame: ~10,000

---

## Security Considerations

**Threat Model:**
- UDP is unauthenticated and unencrypted
- Suitable for trusted local networks only

**Recommendations:**
- Use private networks (192.168.x.x)
- Avoid broadcast mode in production
- Consider VPN/IPsec for untrusted networks
- Future: Add HMAC authentication to header

---

## Test Vectors

### Example Packet 1: No CRC (3 points)

```
# Header (27 bytes)
52 56 49 4C              # magic: 0x4C495652 ("LIVR")
01                       # version: 1
00 10 A5 D4 E8 00 00 00  # device_timestamp: 1000000000000 ns
2A 00 00 00              # seq: 42
03 00                    # point_count: 3
00 00                    # flags: 0
00 00                    # sensor_id: 0
00 00 00 00              # crc32: 0 (disabled)

# Point 0 (13 bytes)
00 00 80 3F              # x: 1.0 (float LE)
00 00 00 40              # y: 2.0 (float LE)
00 00 40 40              # z: 3.0 (float LE)
80                       # intensity: 128

# Point 1 (13 bytes)
00 00 00 40              # x: 2.0
00 00 80 40              # y: 4.0
00 00 C0 40              # z: 6.0
FF                       # intensity: 255

# Point 2 (13 bytes)
00 00 00 00              # x: 0.0
00 00 00 00              # y: 0.0
00 00 80 3F              # z: 1.0
40                       # intensity: 64

# Total: 27 + 3*13 = 66 bytes
```

### Example Packet 2: With CRC32 (2 points)

```
# Header (27 bytes)
52 56 49 4C              # magic: 0x4C495652 ("LIVR")
01                       # version: 1
80 96 98 00 00 00 00 00  # device_timestamp: 10000000 ns
01 00 00 00              # seq: 1
02 00                    # point_count: 2
00 00                    # flags: 0
00 00                    # sensor_id: 0
A3 B2 C1 D4              # crc32: 0xD4C1B2A3 (example, calculated over 23+26 bytes)

# Point 0 (13 bytes)
00 00 00 3F              # x: 0.5
00 00 00 3F              # y: 0.5
00 00 00 40              # z: 2.0
64                       # intensity: 100

# Point 1 (13 bytes)
00 00 80 3F              # x: 1.0
00 00 80 3F              # y: 1.0
00 00 40 40              # z: 3.0
C8                       # intensity: 200

# Total: 27 + 2*13 = 53 bytes
# CRC32 computed over first 23 header bytes + 26 payload bytes = 49 bytes
```

### CRC32 Calculation Example

```c
// CRC32 IEEE 802.3 (polynomial: 0xEDB88320 reflected)
// Calculated over: header[0..22] + payload (EXCLUDES CRC field itself)

uint8_t buffer[1400];

// 1. Fill header (first 23 bytes, CRC field = 0 initially)
struct PacketHeader header;
header.magic = 0x4C495652;
header.version = 1;
header.device_timestamp = device_ts;
header.seq = seq_num;
header.point_count = count;
header.flags = 0;
header.sensor_id = 0;
header.crc32 = 0;  // Will be calculated

memcpy(buffer, &header, 23);  // Copy first 23 bytes (exclude CRC)

// 2. Fill payload (points)
memcpy(buffer + 27, points, count * 13);

// 3. Calculate CRC over header[0..22] + payload
size_t crc_data_size = 23 + (count * 13);
uint32_t crc = crc32_ieee802_3(buffer, crc_data_size);

// 4. Write CRC to buffer[23..26]
memcpy(buffer + 23, &crc, 4);

// 5. Send complete packet (27 + count*13 bytes)
sendto(socket, buffer, 27 + count*13, ...);
```

**Test Vectors** (IEEE 802.3):
- `"123456789"` → `0xCBF43926`
- Empty data → `0x00000000`
- `"The quick brown fox jumps over the lazy dog"` → `0x414FA339`

### Validation (Python)

```python
import struct
import zlib

# Example packet (no CRC)
data = bytes.fromhex(
    "5256494C01"          # magic, version
    "0010A5D4E8000000"    # timestamp
    "2A000000"            # seq
    "0300"                # count
    "0000"                # flags
    "0000"                # sensor_id
    "00000000"            # crc32 (disabled)
    # Point 0
    "0000803F000000400000404080"
    # Point 1
    "00000040000080400000C040FF"
    # Point 2
    "000000000000000000008 03F40"
)

# Parse header
magic, version, ts, seq, count, flags, sid, crc = struct.unpack('<IBIQHHHII', data[:27])

assert magic == 0x4C495652, f"Invalid magic: 0x{magic:08X}"
assert version == 1, f"Invalid version: {version}"
assert count == 3, f"Invalid count: {count}"

# Parse points
for i in range(count):
    offset = 27 + i*13
    x, y, z, intensity = struct.unpack('<fffB', data[offset:offset+13])
    print(f"Point {i}: ({x:.1f}, {y:.1f}, {z:.1f}) intensity={intensity}")

# Verify CRC (if enabled)
if crc != 0:
    # CRC over first 23 header bytes + payload
    crc_data = data[:23] + data[27:]  # Exclude CRC field itself
    calculated_crc = zlib.crc32(crc_data) & 0xFFFFFFFF
    assert crc == calculated_crc, f"CRC mismatch: {crc:08X} != {calculated_crc:08X}"
    print(f"✓ CRC valid: 0x{crc:08X}")
```

### CRC32 Test Cases

**Test Case 1: Empty payload (0 points)**
```
Input:  Header only (23 bytes, no points)
CRC:    0x00000000 (by convention, no CRC for zero points)
```

**Test Case 2: Single point**
```
Input:  23 header bytes + 13 point bytes = 36 bytes
        [52 56 49 4C 01 ... ] (header)
        [00 00 80 3F ... 64] (point: x=1.0, y=1.0, z=1.0, i=100)
CRC:    0x12345678 (example, use crc32_calculate())
```

**Test Case 3: Maximum points (105 points)**
```
Input:  23 + 105*13 = 1388 bytes
CRC:    Calculated over all 1388 bytes
```

---

## References

- **Livox SDK2:** https://github.com/Livox-SDK/Livox-SDK2
- **IEEE 754 Floating Point:** https://en.wikipedia.org/wiki/IEEE_754
- **CRC32 (IEEE 802.3):** https://en.wikipedia.org/wiki/Cyclic_redundancy_check
- **REP-103 (ROS Coordinate Frames):** https://www.ros.org/reps/rep-0103.html

---

## Changelog

**Version 1 (2025-11-02):**
- Initial protocol specification
- 27-byte header with magic, version, timestamp, sequence
- 13-byte point structure (x, y, z, intensity)
- Little-endian encoding
- CRC32 support (optional)

---

**Maintained by:** AIM Robotics
**Contact:** See repository documentation
