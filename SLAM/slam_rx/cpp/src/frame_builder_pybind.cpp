#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/numpy.h>
#include "frame_builder_cpp.hpp"
#include <chrono>
#include <atomic>
#include <iostream>

namespace py = pybind11;
using namespace frame_builder;

// Pybind11 profiling counters
static std::atomic<uint64_t> g_pybind_validate_us{0};
static std::atomic<uint64_t> g_pybind_getptr_us{0};
static std::atomic<uint64_t> g_pybind_cpp_call_us{0};
static std::atomic<uint64_t> g_pybind_dict_us{0};
static std::atomic<uint64_t> g_pybind_sync_us{0};
static std::atomic<size_t> g_pybind_calls{0};
static std::atomic<size_t> g_pybind_dict_creates{0};

// ============================================================================
// Helper: Convert Frame to Python dict (matching Python API)
// ============================================================================

py::object frame_to_dict(const Frame& frame) {
    py::dict result;

    // Create NumPy array for xyz with capsule-based ownership
    auto* xyz_data = new float[frame.point_count * 3];
    std::memcpy(xyz_data, frame.xyz_data.data(), frame.point_count * 3 * sizeof(float));

    py::capsule xyz_capsule(xyz_data, [](void* p) {
        delete[] static_cast<float*>(p);
    });

    std::vector<py::ssize_t> xyz_shape = {static_cast<py::ssize_t>(frame.point_count), 3};
    std::vector<py::ssize_t> xyz_strides = {3 * sizeof(float), sizeof(float)};

    py::array_t<float> xyz_array(
        xyz_shape,
        xyz_strides,
        xyz_data,
        xyz_capsule
    );

    // Build dict matching Python Frame dataclass
    result["xyz"] = xyz_array;
    result["start_ts_ns"] = frame.start_ts_ns;
    result["end_ts_ns"] = frame.end_ts_ns;
    result["seq_first"] = frame.seq_first;
    result["seq_last"] = frame.seq_last;
    result["pkt_count"] = frame.pkt_count;
    result["point_count"] = frame.point_count;

    return result;
}

// ============================================================================
// Python-compatible wrapper for FrameBuilder
// ============================================================================

class FrameBuilderPy {
public:
    explicit FrameBuilderPy(double frame_period_s,
                            size_t max_frame_points,
                            py::object stats_obj)
        : stats_(),
          external_stats_(stats_obj),
          builder_(frame_period_s, max_frame_points, stats_)
    {
        // Initialize external stats if provided
        if (!external_stats_.is_none()) {
            sync_stats_to_python();
        }
    }

    // Add packet (accepts NumPy array)
    py::object add_packet(int64_t device_ts_ns,
                          py::array_t<float> points_xyz,
                          uint32_t seq,
                          bool debug = false)
    {
        g_pybind_calls++;
        auto t0 = std::chrono::high_resolution_clock::now();

        // Validate input array
        if (points_xyz.ndim() != 2 || points_xyz.shape(1) != 3) {
            throw std::runtime_error("points_xyz must be (N, 3) array");
        }
        auto t1 = std::chrono::high_resolution_clock::now();

        // Get direct pointer to data (zero-copy)
        const float* xyz_data = points_xyz.data();
        size_t point_count = points_xyz.shape(0);
        auto t2 = std::chrono::high_resolution_clock::now();

        // Call C++ method
        auto result = builder_.add_packet(device_ts_ns, xyz_data, point_count, seq, debug);
        auto t3 = std::chrono::high_resolution_clock::now();

        // Sync stats only when frame is closed (major performance optimization)
        if (result.has_value() && !external_stats_.is_none()) {
            sync_stats_to_python();
        }
        auto t4 = std::chrono::high_resolution_clock::now();

        // Record timing
        g_pybind_validate_us += std::chrono::duration_cast<std::chrono::microseconds>(t1 - t0).count();
        g_pybind_getptr_us += std::chrono::duration_cast<std::chrono::microseconds>(t2 - t1).count();
        g_pybind_cpp_call_us += std::chrono::duration_cast<std::chrono::microseconds>(t3 - t2).count();
        g_pybind_sync_us += std::chrono::duration_cast<std::chrono::microseconds>(t4 - t3).count();

        // Return None or Frame dict
        if (!result.has_value()) {
            return py::none();
        }

        auto t5 = std::chrono::high_resolution_clock::now();
        auto dict = frame_to_dict(*result);
        auto t6 = std::chrono::high_resolution_clock::now();

        g_pybind_dict_creates++;
        g_pybind_dict_us += std::chrono::duration_cast<std::chrono::microseconds>(t6 - t5).count();

        return dict;
    }

    // Add batch of packets (returns list of completed frames)
    py::list add_packets_batch(
        py::list device_ts_ns_batch,
        py::list xyz_batch,
        py::list seq_batch,
        bool debug = false)
    {
        const size_t batch_size = py::len(device_ts_ns_batch);

        // Validate input sizes
        if (py::len(xyz_batch) != batch_size || py::len(seq_batch) != batch_size) {
            throw std::runtime_error("Batch size mismatch: timestamps, xyz, and seq must have same length");
        }

        if (batch_size == 0) {
            return py::list();  // Empty batch -> empty result
        }

        // Extract data from Python lists
        std::vector<int64_t> ts_vec;
        std::vector<const float*> xyz_ptrs;
        std::vector<size_t> point_counts;
        std::vector<uint32_t> seq_vec;

        ts_vec.reserve(batch_size);
        xyz_ptrs.reserve(batch_size);
        point_counts.reserve(batch_size);
        seq_vec.reserve(batch_size);

        // Keep NumPy arrays alive during C++ processing
        std::vector<py::array_t<float>> xyz_arrays;
        xyz_arrays.reserve(batch_size);

        for (size_t i = 0; i < batch_size; ++i) {
            // Extract timestamp
            ts_vec.push_back(device_ts_ns_batch[i].cast<int64_t>());

            // Extract xyz array
            py::array_t<float> xyz_arr = xyz_batch[i].cast<py::array_t<float>>();
            if (xyz_arr.ndim() != 2 || xyz_arr.shape(1) != 3) {
                throw std::runtime_error(
                    "Invalid array shape at index " + std::to_string(i) +
                    ": expected (N, 3), got (" + std::to_string(xyz_arr.shape(0)) +
                    ", " + std::to_string(xyz_arr.shape(1)) + ")"
                );
            }

            xyz_ptrs.push_back(xyz_arr.data());
            point_counts.push_back(xyz_arr.shape(0));
            xyz_arrays.push_back(xyz_arr);  // Keep alive

            // Extract sequence
            seq_vec.push_back(seq_batch[i].cast<uint32_t>());
        }

        // Call C++ batch method
        auto frames = builder_.add_packets_batch(
            ts_vec.data(),
            xyz_ptrs.data(),
            point_counts.data(),
            seq_vec.data(),
            batch_size,
            debug
        );

        // Convert frames to Python dicts
        py::list result;
        for (const auto& frame : frames) {
            result.append(frame_to_dict(frame));
        }

        // Sync stats once per batch (major optimization!)
        if (!frames.empty() && !external_stats_.is_none()) {
            sync_stats_to_python();
        }

        return result;
    }

    // Flush remaining frame
    py::object flush(bool debug = false) {
        auto result = builder_.flush(debug);

        // Sync stats
        if (!external_stats_.is_none()) {
            sync_stats_to_python();
        }

        if (!result.has_value()) {
            return py::none();
        }

        return frame_to_dict(*result);
    }

    // Reset state
    void reset() {
        builder_.reset();

        if (!external_stats_.is_none()) {
            sync_stats_to_python();
        }
    }

    // Get statistics
    const FrameBuilderStats& stats() const {
        return builder_.stats();
    }

private:
    FrameBuilderStats stats_;           // Internal C++ stats
    py::object external_stats_;         // Optional external Python stats object
    FrameBuilder builder_;              // C++ frame builder

    // Sync internal C++ stats to external Python stats object
    void sync_stats_to_python() {
        const auto& s = builder_.stats();
        external_stats_.attr("frames_built") = s.frames_built;
        external_stats_.attr("packets_added") = s.packets_added;
        external_stats_.attr("points_added") = s.points_added;
        external_stats_.attr("late_packets") = s.late_packets;
        external_stats_.attr("seq_gaps") = s.seq_gaps;
        external_stats_.attr("seq_reorders") = s.seq_reorders;
        external_stats_.attr("overflow_frames") = s.overflow_frames;
    }
};

// ============================================================================
// Pybind11 profiling export
// ============================================================================

void print_pybind_profiling_stats() {
    std::cerr << "\n========================================\n";
    std::cerr << "Pybind11 Profiling Statistics\n";
    std::cerr << "========================================\n";

    std::cerr << "Total add_packet calls: " << g_pybind_calls << "\n";
    std::cerr << "Frame dicts created: " << g_pybind_dict_creates << "\n";

    if (g_pybind_calls > 0) {
        double avg_validate = static_cast<double>(g_pybind_validate_us) / g_pybind_calls;
        double avg_getptr = static_cast<double>(g_pybind_getptr_us) / g_pybind_calls;
        double avg_cpp = static_cast<double>(g_pybind_cpp_call_us) / g_pybind_calls;
        double avg_sync = static_cast<double>(g_pybind_sync_us) / g_pybind_calls;

        std::cerr << "\nAverage per add_packet call:\n";
        std::cerr << "  Validation:  " << avg_validate << " μs\n";
        std::cerr << "  Get pointer: " << avg_getptr << " μs\n";
        std::cerr << "  C++ call:    " << avg_cpp << " μs\n";
        std::cerr << "  Stats sync:  " << avg_sync << " μs\n";
        std::cerr << "  TOTAL:       " << (avg_validate + avg_getptr + avg_cpp + avg_sync) << " μs\n";
    }

    if (g_pybind_dict_creates > 0) {
        double avg_dict = static_cast<double>(g_pybind_dict_us) / g_pybind_dict_creates;
        std::cerr << "\nDict creation:\n";
        std::cerr << "  Average: " << avg_dict << " μs/dict\n";
        std::cerr << "  Total:   " << g_pybind_dict_us << " μs\n";
    }

    std::cerr << "========================================\n\n";
}

// ============================================================================
// pybind11 module definition
// ============================================================================

PYBIND11_MODULE(frame_builder_cpp, m) {
    m.doc() = "Frame Builder - C++ Optimized Version";

    // FrameBuilderStats class
    py::class_<FrameBuilderStats>(m, "FrameBuilderStats")
        .def(py::init<>())
        .def_readwrite("frames_built", &FrameBuilderStats::frames_built)
        .def_readwrite("packets_added", &FrameBuilderStats::packets_added)
        .def_readwrite("points_added", &FrameBuilderStats::points_added)
        .def_readwrite("late_packets", &FrameBuilderStats::late_packets)
        .def_readwrite("seq_gaps", &FrameBuilderStats::seq_gaps)
        .def_readwrite("seq_reorders", &FrameBuilderStats::seq_reorders)
        .def_readwrite("overflow_frames", &FrameBuilderStats::overflow_frames)
        .def("reset", &FrameBuilderStats::reset)
        .def("__repr__", &FrameBuilderStats::repr);

    // FrameBuilder class (Python-compatible wrapper)
    py::class_<FrameBuilderPy>(m, "FrameBuilder")
        .def(py::init<double, size_t, py::object>(),
             py::arg("frame_period_s"),
             py::arg("max_frame_points") = 120000,
             py::arg("stats") = py::none(),
             "Initialize Frame Builder\n\n"
             "Args:\n"
             "    frame_period_s (float): Frame duration in seconds\n"
             "    max_frame_points (int): Maximum points per frame (default: 120000)\n"
             "    stats (FrameBuilderStats): Optional external stats object")
        .def("add_packet", &FrameBuilderPy::add_packet,
             py::arg("device_ts_ns"),
             py::arg("points_xyz"),
             py::arg("seq"),
             py::arg("debug") = false,
             "Add packet to current frame\n\n"
             "Args:\n"
             "    device_ts_ns (int): Device timestamp in nanoseconds\n"
             "    points_xyz (np.ndarray): Point cloud (N, 3) float32\n"
             "    seq (int): Sequence number\n"
             "    debug (bool): Enable debug logging\n\n"
             "Returns:\n"
             "    dict or None: Completed frame or None\n"
             "        {\n"
             "            'xyz': np.ndarray (N, 3),\n"
             "            'start_ts_ns': int,\n"
             "            'end_ts_ns': int,\n"
             "            'seq_first': int,\n"
             "            'seq_last': int,\n"
             "            'pkt_count': int,\n"
             "            'point_count': int\n"
             "        }")
        .def("add_packets_batch", &FrameBuilderPy::add_packets_batch,
             py::arg("device_ts_ns_batch"),
             py::arg("xyz_batch"),
             py::arg("seq_batch"),
             py::arg("debug") = false,
             "Add batch of packets to frame builder\n\n"
             "Args:\n"
             "    device_ts_ns_batch (list[int]): List of timestamps in nanoseconds\n"
             "    xyz_batch (list[np.ndarray]): List of point clouds (each N×3 float32)\n"
             "    seq_batch (list[int]): List of sequence numbers\n"
             "    debug (bool): Enable debug logging\n\n"
             "Returns:\n"
             "    list[dict]: List of completed frames (may be empty)\n"
             "        Each frame is a dict with keys:\n"
             "            'xyz': np.ndarray (N, 3)\n"
             "            'start_ts_ns': int\n"
             "            'end_ts_ns': int\n"
             "            'seq_first': int\n"
             "            'seq_last': int\n"
             "            'pkt_count': int\n"
             "            'point_count': int")
        .def("flush", &FrameBuilderPy::flush,
             py::arg("debug") = false,
             "Flush remaining frame\n\n"
             "Args:\n"
             "    debug (bool): Enable debug logging\n\n"
             "Returns:\n"
             "    dict or None: Remaining frame or None")
        .def("reset", &FrameBuilderPy::reset,
             "Reset frame builder state")
        .def_property_readonly("stats", &FrameBuilderPy::stats,
                               "Get frame builder statistics");

    // Profiling functions
    m.def("print_cpp_profiling_stats", &frame_builder::print_profiling_stats,
          "Print C++ internal profiling statistics");
    m.def("print_pybind_profiling_stats", &print_pybind_profiling_stats,
          "Print pybind11 boundary profiling statistics");
}
