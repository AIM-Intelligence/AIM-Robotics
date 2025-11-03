#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/numpy.h>
#include "lidar_protocol_cpp.hpp"

namespace py = pybind11;

// Helper: Convert ParsedPacket to Python dict (matching Python API)
py::object packet_to_dict(const ParsedPacket& packet) {
    py::dict result;

    result["device_ts_ns"] = packet.device_ts_ns;
    result["seq"] = packet.seq;
    result["point_count"] = packet.point_count;
    result["sensor_id"] = packet.sensor_id;
    result["flags"] = packet.flags;
    result["crc32"] = packet.crc32;

    // Create NumPy arrays with zero-copy (data ownership transferred to Python)
    size_t n_points = packet.point_count;

    // points: (N, 4) array
    auto* points_data = new float[n_points * 4];
    std::memcpy(points_data, packet.points_data.data(), n_points * 4 * sizeof(float));

    py::capsule points_capsule(points_data, [](void* p) {
        delete[] static_cast<float*>(p);
    });

    std::vector<py::ssize_t> points_shape = {static_cast<py::ssize_t>(n_points), 4};
    std::vector<py::ssize_t> points_strides = {4 * sizeof(float), sizeof(float)};

    py::array_t<float> points(
        points_shape,
        points_strides,
        points_data,
        points_capsule
    );

    // xyz: (N, 3) array
    auto* xyz_data = new float[n_points * 3];
    std::memcpy(xyz_data, packet.xyz_data.data(), n_points * 3 * sizeof(float));

    py::capsule xyz_capsule(xyz_data, [](void* p) {
        delete[] static_cast<float*>(p);
    });

    std::vector<py::ssize_t> xyz_shape = {static_cast<py::ssize_t>(n_points), 3};
    std::vector<py::ssize_t> xyz_strides = {3 * sizeof(float), sizeof(float)};

    py::array_t<float> xyz(
        xyz_shape,
        xyz_strides,
        xyz_data,
        xyz_capsule
    );

    result["points"] = points;
    result["xyz"] = xyz;

    return result;
}

// Python-compatible wrapper for LidarProtocol
class LidarProtocolPy {
public:
    explicit LidarProtocolPy(bool validate_crc = true, py::object stats = py::none())
        : protocol_(validate_crc), external_stats_(stats) {}

    // Parse datagram (accepts Python bytes)
    py::object parse_datagram(py::bytes data, bool debug = false) {
        // Extract raw bytes from Python bytes object
        char* buffer;
        ssize_t length;
        if (PYBIND11_BYTES_AS_STRING_AND_SIZE(data.ptr(), &buffer, &length) == -1) {
            throw std::runtime_error("Failed to extract bytes");
        }

        // Call C++ parser
        auto result = protocol_.parse_datagram(
            reinterpret_cast<const uint8_t*>(buffer),
            static_cast<size_t>(length),
            debug
        );

        // Sync stats to external Python object if provided
        if (!external_stats_.is_none()) {
            sync_stats_to_python();
        }

        // Return None if parsing failed (matching Python behavior)
        if (!result.has_value()) {
            return py::none();
        }

        // Convert to Python dict
        return packet_to_dict(*result);
    }

    // CRC32 calculation (for testing/debugging)
    uint32_t crc32_ieee802_3(py::bytes data) {
        char* buffer;
        ssize_t length;
        if (PYBIND11_BYTES_AS_STRING_AND_SIZE(data.ptr(), &buffer, &length) == -1) {
            throw std::runtime_error("Failed to extract bytes");
        }

        return protocol_.crc32_ieee(
            reinterpret_cast<const uint8_t*>(buffer),
            static_cast<size_t>(length)
        );
    }

    // Get statistics
    const ProtocolStats& stats() const { return protocol_.stats(); }

private:
    LidarProtocol protocol_;
    py::object external_stats_;  // Optional external stats object

    // Sync internal C++ stats to external Python stats object
    void sync_stats_to_python() {
        const auto& s = protocol_.stats();
        external_stats_.attr("total_packets") = s.total_packets;
        external_stats_.attr("valid_packets") = s.valid_packets;
        external_stats_.attr("crc_failures") = s.crc_failures;
        external_stats_.attr("bad_magic") = s.bad_magic;
        external_stats_.attr("bad_version") = s.bad_version;
        external_stats_.attr("len_mismatch") = s.len_mismatch;
        external_stats_.attr("invalid_count") = s.invalid_count;
    }
};

// pybind11 module definition
PYBIND11_MODULE(lidar_protocol_cpp, m) {
    m.doc() = "LiDAR Protocol Parser - C++ Optimized Version";

    // Protocol constants
    m.attr("MAGIC") = LIDAR_MAGIC;
    m.attr("VERSION") = LIDAR_VERSION;
    m.attr("HEADER_SIZE") = HEADER_SIZE;
    m.attr("POINT_SIZE") = POINT_SIZE;
    m.attr("MAX_POINTS_PER_PACKET") = MAX_POINTS_PER_PACKET;

    // ProtocolStats class
    py::class_<ProtocolStats>(m, "ProtocolStats")
        .def(py::init<>())
        .def_readwrite("total_packets", &ProtocolStats::total_packets)
        .def_readwrite("valid_packets", &ProtocolStats::valid_packets)
        .def_readwrite("crc_failures", &ProtocolStats::crc_failures)
        .def_readwrite("bad_magic", &ProtocolStats::bad_magic)
        .def_readwrite("bad_version", &ProtocolStats::bad_version)
        .def_readwrite("len_mismatch", &ProtocolStats::len_mismatch)
        .def_readwrite("invalid_count", &ProtocolStats::invalid_count)
        .def("reset", &ProtocolStats::reset)
        .def("__repr__", &ProtocolStats::repr);

    // LidarProtocol class (Python-compatible wrapper)
    py::class_<LidarProtocolPy>(m, "LidarProtocol")
        .def(py::init<bool, py::object>(),
             py::arg("validate_crc") = true,
             py::arg("stats") = py::none(),
             "Initialize LiDAR protocol parser\n\n"
             "Args:\n"
             "    validate_crc (bool): Enable CRC32 validation (default: True)\n"
             "    stats (ProtocolStats): Optional external stats object")
        .def("parse_datagram", &LidarProtocolPy::parse_datagram,
             py::arg("datagram"),
             py::arg("debug") = false,
             "Parse a single UDP datagram\n\n"
             "Args:\n"
             "    datagram (bytes): Raw UDP packet bytes\n"
             "    debug (bool): Enable debug logging\n\n"
             "Returns:\n"
             "    dict or None: Parsed packet data or None if invalid\n"
             "        {\n"
             "            'device_ts_ns': int,\n"
             "            'seq': int,\n"
             "            'point_count': int,\n"
             "            'sensor_id': int,\n"
             "            'flags': int,\n"
             "            'crc32': int,\n"
             "            'points': np.ndarray (N, 4) [x, y, z, intensity],\n"
             "            'xyz': np.ndarray (N, 3) [x, y, z only]\n"
             "        }")
        .def("crc32_ieee802_3", &LidarProtocolPy::crc32_ieee802_3,
             py::arg("data"),
             "Calculate IEEE 802.3 CRC32\n\n"
             "Args:\n"
             "    data (bytes): Input bytes\n\n"
             "Returns:\n"
             "    int: CRC32 checksum (uint32)")
        .def_property_readonly("stats", &LidarProtocolPy::stats,
                               "Get protocol statistics");
}
