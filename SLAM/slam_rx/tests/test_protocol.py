#!/usr/bin/env python3
"""
Unit tests for LiDAR Protocol Parser

Tests packet parsing, CRC validation, and error handling.
"""

import struct
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from lidar_protocol import LidarProtocol, ProtocolStats


def test_valid_packet_no_crc():
    """Test valid packet without CRC"""
    print("\n" + "="*70)
    print("TEST 1: Valid packet (CRC disabled)")
    print("="*70)

    # Build packet
    # Format: I B Q I H H H I (magic, ver, ts, seq, count, flags, sensor, crc)
    header = struct.pack('<IBQIHHHI',
                        0x4C495652,    # magic (4B)
                        1,             # version (1B)
                        1000000000,    # timestamp (8B)
                        42,            # seq (4B)
                        2,             # point_count (2B)
                        0,             # flags (2B)
                        0,             # sensor_id (2B)
                        0)             # crc32 (4B)

    point1 = struct.pack('<fffB', 1.0, 2.0, 3.0, 128)
    point2 = struct.pack('<fffB', 4.0, 5.0, 6.0, 255)

    packet = header + point1 + point2

    # Parse
    parser = LidarProtocol(validate_crc=False)
    result = parser.parse_datagram(packet, debug=True)

    assert result is not None, "Parsing failed"
    assert result['device_ts_ns'] == 1000000000
    assert result['seq'] == 42
    assert result['point_count'] == 2
    assert result['xyz'].shape == (2, 3)
    assert abs(result['xyz'][0, 0] - 1.0) < 0.001
    assert abs(result['xyz'][1, 2] - 6.0) < 0.001

    print(f"✓ Test passed: {parser.stats}")
    return True


def test_valid_packet_with_crc():
    """Test valid packet with CRC"""
    print("\n" + "="*70)
    print("TEST 2: Valid packet (CRC enabled)")
    print("="*70)

    # Build packet WITHOUT CRC first
    # Format: I B Q I H H H (magic, ver, ts, seq, count, flags, sensor)
    header_no_crc = struct.pack('<IBQIHHH',
                                0x4C495652,    # magic (4B)
                                1,             # version (1B)
                                2000000000,    # timestamp (8B)
                                100,           # seq (4B)
                                1,             # point_count (2B)
                                0,             # flags (2B)
                                0)             # sensor_id (2B)

    point1 = struct.pack('<fffB', 5.0, 6.0, 7.0, 200)

    # Calculate CRC over header[0..22] + payload
    crc_data = header_no_crc + point1
    import zlib
    crc = zlib.crc32(crc_data) & 0xFFFFFFFF

    # Now build full header with CRC
    header_with_crc = header_no_crc + struct.pack('<I', crc)
    packet = header_with_crc + point1

    print(f"Calculated CRC: 0x{crc:08X}")

    # Parse with CRC validation
    parser = LidarProtocol(validate_crc=True)
    result = parser.parse_datagram(packet, debug=True)

    assert result is not None, "Parsing failed"
    assert result['crc32'] == crc
    assert result['seq'] == 100
    assert result['point_count'] == 1

    print(f"✓ Test passed: {parser.stats}")
    return True


def test_crc_mismatch():
    """Test CRC validation failure"""
    print("\n" + "="*70)
    print("TEST 3: CRC mismatch (should fail)")
    print("="*70)

    # Build packet with WRONG CRC
    header = struct.pack('<IBQIHHHI',
                        0x4C495652,
                        1,
                        3000000000,
                        200,
                        1,
                        0,
                        0,
                        0xDEADBEEF)    # Wrong CRC!

    point1 = struct.pack('<fffB', 1.0, 1.0, 1.0, 100)
    packet = header + point1

    # Parse with CRC validation
    parser = LidarProtocol(validate_crc=True)
    result = parser.parse_datagram(packet, debug=True)

    assert result is None, "Should have failed CRC validation"
    assert parser.stats.crc_failures == 1

    print(f"✓ Test passed (correctly rejected): {parser.stats}")
    return True


def test_bad_magic():
    """Test bad magic number"""
    print("\n" + "="*70)
    print("TEST 4: Bad magic number (should fail)")
    print("="*70)

    # Build packet with WRONG magic
    header = struct.pack('<IBQIHHHI',
                        0xDEADBEEF,    # Wrong magic!
                        1,
                        4000000000,
                        300,
                        1,
                        0,
                        0,
                        0)

    point1 = struct.pack('<fffB', 1.0, 1.0, 1.0, 100)
    packet = header + point1

    parser = LidarProtocol(validate_crc=False)
    result = parser.parse_datagram(packet, debug=True)

    assert result is None, "Should have failed magic check"
    assert parser.stats.bad_magic == 1

    print(f"✓ Test passed (correctly rejected): {parser.stats}")
    return True


def test_length_mismatch():
    """Test packet length mismatch"""
    print("\n" + "="*70)
    print("TEST 5: Length mismatch (should fail)")
    print("="*70)

    # Build header claiming 3 points, but only 1 point in payload
    header = struct.pack('<IBQIHHHI',
                        0x4C495652,
                        1,
                        5000000000,
                        400,
                        3,             # Claims 3 points!
                        0,
                        0,
                        0)

    point1 = struct.pack('<fffB', 1.0, 1.0, 1.0, 100)
    packet = header + point1  # Only 1 point

    parser = LidarProtocol(validate_crc=False)
    result = parser.parse_datagram(packet, debug=True)

    assert result is None, "Should have failed length check"
    assert parser.stats.len_mismatch == 1

    print(f"✓ Test passed (correctly rejected): {parser.stats}")
    return True


def test_invalid_point_count():
    """Test invalid point count"""
    print("\n" + "="*70)
    print("TEST 6: Invalid point count (should fail)")
    print("="*70)

    # Build packet with point_count = 0 (invalid)
    header = struct.pack('<IBQIHHHI',
                        0x4C495652,
                        1,
                        6000000000,
                        500,
                        0,             # Invalid: must be >= 1
                        0,
                        0,
                        0)

    packet = header  # No points

    parser = LidarProtocol(validate_crc=False)
    result = parser.parse_datagram(packet, debug=True)

    assert result is None, "Should have failed count check"
    assert parser.stats.invalid_count == 1

    print(f"✓ Test passed (correctly rejected): {parser.stats}")
    return True


def run_all_tests():
    """Run all tests"""
    print("\n" + "="*70)
    print("LiDAR Protocol Parser - Unit Tests")
    print("="*70)

    tests = [
        test_valid_packet_no_crc,
        test_valid_packet_with_crc,
        test_crc_mismatch,
        test_bad_magic,
        test_length_mismatch,
        test_invalid_point_count
    ]

    passed = 0
    failed = 0

    for test_func in tests:
        try:
            if test_func():
                passed += 1
        except AssertionError as e:
            print(f"✗ Test FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ Test ERROR: {e}")
            failed += 1

    print("\n" + "="*70)
    print(f"RESULTS: {passed}/{len(tests)} passed, {failed} failed")
    print("="*70 + "\n")

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
