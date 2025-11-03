"""
LiDAR Protocol Parser

Parses UDP datagrams from lidar_stream transmitter.

Protocol Format (Little-Endian):
  Header (27 bytes):
    - magic[4]:            0x4C495652 ("LIVR")
    - version[1]:          1
    - device_timestamp[8]: nanoseconds (uint64)
    - seq[4]:              sequence number (uint32)
    - point_count[2]:      number of points (uint16, 1-105)
    - flags[2]:            reserved (uint16)
    - sensor_id[2]:        sensor ID (uint16)
    - crc32[4]:            IEEE 802.3 checksum (uint32)

  Points (13 bytes each × point_count):
    - x[4]: float32 (meters)
    - y[4]: float32 (meters)
    - z[4]: float32 (meters)
    - intensity[1]: uint8 (0-255)

CRC32: Calculated over header[0..22] + all payload (excludes CRC field itself)
"""

import struct
import numpy as np
from typing import Optional, Dict
import zlib


class ProtocolStats:
    """Statistics tracking for protocol errors"""

    def __init__(self):
        self.total_packets = 0
        self.valid_packets = 0
        self.crc_failures = 0
        self.bad_magic = 0
        self.bad_version = 0
        self.len_mismatch = 0
        self.invalid_count = 0

    def reset(self):
        """Reset all counters"""
        self.__init__()

    def __repr__(self):
        return (f"ProtocolStats(total={self.total_packets}, valid={self.valid_packets}, "
                f"crc_fail={self.crc_failures}, bad_magic={self.bad_magic}, "
                f"bad_ver={self.bad_version}, len_err={self.len_mismatch}, "
                f"count_err={self.invalid_count})")


class LidarProtocol:
    """LiDAR Stream  Protocol Parser"""

    # Protocol constants
    MAGIC = 0x4C495652  # "LIVR" in little-endian
    VERSION = 1
    HEADER_SIZE = 27
    POINT_SIZE = 13
    MAX_POINTS_PER_PACKET = 105

    def __init__(self, validate_crc: bool = True, stats: Optional[ProtocolStats] = None):
        """
        Initialize protocol parser

        Args:
            validate_crc: Enable CRC32 validation (default: True)
            stats: Statistics object to update (creates new if None)
        """
        self.validate_crc = validate_crc
        self.stats = stats if stats is not None else ProtocolStats()

    @staticmethod
    def crc32_ieee802_3(data: bytes) -> int:
        """
        Calculate IEEE 802.3 CRC32

        Args:
            data: Input bytes

        Returns:
            CRC32 checksum (uint32)
        """
        return zlib.crc32(data) & 0xFFFFFFFF

    def parse_datagram(self, datagram: bytes, debug: bool = False) -> Optional[Dict]:
        """
        Parse a single UDP datagram

        Args:
            datagram: Raw UDP packet bytes
            debug: Enable debug logging

        Returns:
            Dictionary with parsed data or None if invalid:
            {
                'device_ts_ns': int,
                'seq': int,
                'point_count': int,
                'sensor_id': int,
                'flags': int,
                'crc32': int,
                'points': np.ndarray (N, 4) [x, y, z, intensity],
                'xyz': np.ndarray (N, 3) [x, y, z only]
            }
        """
        self.stats.total_packets += 1

        # 1. Length check (minimum: header only)
        if len(datagram) < self.HEADER_SIZE:
            self.stats.len_mismatch += 1
            if debug:
                print(f"[PROTO] Length too short: {len(datagram)} < {self.HEADER_SIZE}")
            return None

        # 2. Parse header (27 bytes, little-endian)
        # Format: magic(4) ver(1) ts(8) seq(4) count(2) flags(2) sensor(2) crc(4)
        # Struct format: I B Q I H H H I (total 27 bytes)
        try:
            header = struct.unpack('<IBQIHHHI', datagram[:self.HEADER_SIZE])
        except struct.error as e:
            self.stats.len_mismatch += 1
            if debug:
                print(f"[PROTO] Header unpack error: {e}")
            return None

        magic, version, device_ts_ns, seq, point_count, flags, sensor_id, crc32 = header

        # 3. Validate magic
        if magic != self.MAGIC:
            self.stats.bad_magic += 1
            if debug:
                print(f"[PROTO] Bad magic: 0x{magic:08X} != 0x{self.MAGIC:08X}")
            return None

        # 4. Validate version
        if version != self.VERSION:
            self.stats.bad_version += 1
            if debug:
                print(f"[PROTO] Bad version: {version} != {self.VERSION}")
            return None

        # 5. Validate point count
        if point_count < 1 or point_count > self.MAX_POINTS_PER_PACKET:
            self.stats.invalid_count += 1
            if debug:
                print(f"[PROTO] Invalid point_count: {point_count} (valid: 1-{self.MAX_POINTS_PER_PACKET})")
            return None

        # 6. Validate total length
        expected_len = self.HEADER_SIZE + point_count * self.POINT_SIZE
        if len(datagram) != expected_len:
            self.stats.len_mismatch += 1
            if debug:
                print(f"[PROTO] Length mismatch: {len(datagram)} != {expected_len} "
                      f"(header={self.HEADER_SIZE} + {point_count}×{self.POINT_SIZE})")
            return None

        # 7. CRC validation (if enabled and CRC != 0)
        if self.validate_crc and crc32 != 0:
            # CRC over: header[0..22] + payload
            crc_data = datagram[:23] + datagram[27:]  # Exclude CRC field itself
            calculated_crc = self.crc32_ieee802_3(crc_data)

            if calculated_crc != crc32:
                self.stats.crc_failures += 1
                if debug:
                    print(f"[PROTO] CRC mismatch: calculated=0x{calculated_crc:08X} != "
                          f"received=0x{crc32:08X}")
                return None

        # 8. Parse points (13 bytes each: x, y, z floats + intensity uint8)
        points_data = []
        offset = self.HEADER_SIZE

        for i in range(point_count):
            point_bytes = datagram[offset:offset + self.POINT_SIZE]
            x, y, z, intensity = struct.unpack('<fffB', point_bytes)
            points_data.append([x, y, z, intensity])
            offset += self.POINT_SIZE

        # Convert to numpy array
        points = np.array(points_data, dtype=np.float32)  # (N, 4)
        xyz = points[:, :3]  # (N, 3) - for SLAM

        self.stats.valid_packets += 1

        result = {
            'device_ts_ns': device_ts_ns,
            'seq': seq,
            'point_count': point_count,
            'sensor_id': sensor_id,
            'flags': flags,
            'crc32': crc32,
            'points': points,      # Full data with intensity
            'xyz': xyz             # XYZ only for SLAM
        }

        if debug:
            print(f"[PROTO] ✓ Valid packet: seq={seq}, ts={device_ts_ns}, "
                  f"pts={point_count}, crc=0x{crc32:08X}")

        return result


# Convenience function for quick parsing
def parse_lidar_packet(datagram: bytes, validate_crc: bool = True) -> Optional[Dict]:
    """
    Quick parse function (creates parser internally)

    Args:
        datagram: Raw UDP packet
        validate_crc: Enable CRC validation

    Returns:
        Parsed packet dict or None
    """
    parser = LidarProtocol(validate_crc=validate_crc)
    return parser.parse_datagram(datagram)


if __name__ == "__main__":
    # Quick self-test
    print("LiDAR Protocol Parser")
    print("=" * 50)

    # Test vector: minimal valid packet (2 points, no CRC)
    header = struct.pack('<IBQHHHHI',
                        0x4C495652,    # magic
                        1,             # version
                        1000000000,    # timestamp (1 sec)
                        42,            # seq
                        2,             # point_count
                        0,             # flags
                        0,             # sensor_id
                        0)             # crc32 (disabled)

    # 2 points
    point1 = struct.pack('<fffB', 1.0, 2.0, 3.0, 128)
    point2 = struct.pack('<fffB', 4.0, 5.0, 6.0, 255)

    test_packet = header + point1 + point2

    print(f"Test packet size: {len(test_packet)} bytes")
    print(f"Expected: {27 + 2*13} = 53 bytes")

    # Parse without CRC validation (CRC=0)
    parser = LidarProtocol(validate_crc=False)
    result = parser.parse_datagram(test_packet, debug=True)

    if result:
        print("\n✓ Parse successful!")
        print(f"  Timestamp: {result['device_ts_ns']} ns")
        print(f"  Sequence: {result['seq']}")
        print(f"  Points: {result['point_count']}")
        print(f"  XYZ shape: {result['xyz'].shape}")
        print(f"  Points:\n{result['points']}")
    else:
        print("\n✗ Parse failed!")

    print(f"\nStats: {parser.stats}")
