#include "frame_builder_cpp.hpp"
#include <cstring>
#include <iostream>
#include <sstream>
#include <iomanip>
#include <chrono>
#include <atomic>

namespace frame_builder {

// ============================================================================
// Profiling instrumentation
// ============================================================================

static std::atomic<size_t> g_memcpy_calls{0};
static std::atomic<size_t> g_memcpy_bytes{0};
static std::atomic<size_t> g_add_to_frame_calls{0};
static std::atomic<size_t> g_close_frame_calls{0};
static std::atomic<uint64_t> g_add_to_frame_total_us{0};
static std::atomic<uint64_t> g_close_frame_total_us{0};
static std::atomic<uint64_t> g_memcpy_total_us{0};

#define PROFILE_START() auto _prof_start = std::chrono::high_resolution_clock::now()
#define PROFILE_END(name, counter) \
    do { \
        auto _prof_end = std::chrono::high_resolution_clock::now(); \
        auto _prof_dur_us = std::chrono::duration_cast<std::chrono::microseconds>(_prof_end - _prof_start).count(); \
        counter += _prof_dur_us; \
    } while(0)

// ============================================================================
// Frame implementation
// ============================================================================

std::string Frame::repr() const {
    std::ostringstream oss;
    oss << "Frame(pts=" << point_count
        << ", pkts=" << pkt_count
        << ", dur=" << std::fixed << std::setprecision(3) << duration_s() << "s"
        << ", seq=" << seq_first << "-" << seq_last << ")";
    return oss.str();
}

// ============================================================================
// FrameBuilderStats implementation
// ============================================================================

void FrameBuilderStats::reset() {
    frames_built = 0;
    packets_added = 0;
    points_added = 0;
    late_packets = 0;
    seq_gaps = 0;
    seq_reorders = 0;
    overflow_frames = 0;
}

std::string FrameBuilderStats::repr() const {
    std::ostringstream oss;
    oss << "FrameBuilderStats(frames=" << frames_built
        << ", pkts=" << packets_added
        << ", pts=" << points_added
        << ", late=" << late_packets
        << ", gaps=" << seq_gaps
        << ", reorder=" << seq_reorders
        << ", overflow=" << overflow_frames << ")";
    return oss.str();
}

// ============================================================================
// FrameBuilder implementation
// ============================================================================

FrameBuilder::FrameBuilder(double frame_period_s,
                           size_t max_frame_points,
                           FrameBuilderStats& stats)
    : frame_period_ns_(static_cast<int64_t>(frame_period_s * 1e9))
    , max_frame_points_(max_frame_points)
    , stats_(stats)
    , current_point_count_(0)
    , current_frame_start_ts_(-1)
    , current_frame_end_ts_(-1)
    , current_seq_first_(0)
    , current_seq_last_(0)
    , current_pkt_count_(0)
    , last_seq_(std::nullopt)
{
    // Pre-allocate buffer for maximum points (avoids reallocation)
    point_buffer_.reserve(max_frame_points * 3);
}

std::optional<Frame> FrameBuilder::add_packet(
    int64_t device_ts_ns,
    const float* xyz_data,
    size_t point_count,
    uint32_t seq,
    bool debug)
{
    // Initialize first frame if needed
    if (current_frame_start_ts_ < 0) {
        start_new_frame(device_ts_ns, seq);
        if (debug) {
            std::cerr << "[FRAME] Started new frame at ts=" << device_ts_ns << std::endl;
        }
    }

    // Check for late packet (timestamp < frame start)
    if (device_ts_ns < current_frame_start_ts_) {
        stats_.late_packets++;
        if (debug) {
            std::cerr << "[FRAME] Late packet: ts=" << device_ts_ns
                     << " < frame_start=" << current_frame_start_ts_
                     << " (seq=" << seq << ", dropping)" << std::endl;
        }
        return std::nullopt;
    }

    // Check if frame time window expired
    if (device_ts_ns >= current_frame_start_ts_ + frame_period_ns_) {
        // Close current frame and return it
        auto completed_frame = close_current_frame(debug);

        // Start new frame
        start_new_frame(device_ts_ns, seq);
        if (debug) {
            std::cerr << "[FRAME] Started new frame at ts=" << device_ts_ns << std::endl;
        }

        // Add packet to new frame
        add_to_current_frame(device_ts_ns, xyz_data, point_count, seq, debug);

        return completed_frame;
    }

    // Add to current frame
    add_to_current_frame(device_ts_ns, xyz_data, point_count, seq, debug);

    return std::nullopt;
}

std::optional<Frame> FrameBuilder::flush(bool debug) {
    if (current_frame_start_ts_ < 0) {
        // No frame to flush
        return std::nullopt;
    }

    if (debug) {
        std::cerr << "[FRAME] Flushing remaining frame (pts=" << current_point_count_
                 << ", pkts=" << current_pkt_count_ << ")" << std::endl;
    }

    return close_current_frame(debug);
}

std::vector<Frame> FrameBuilder::add_packets_batch(
    const int64_t* device_ts_ns_batch,
    const float* const* xyz_data_batch,
    const size_t* point_counts,
    const uint32_t* seq_batch,
    size_t batch_size,
    bool debug)
{
    std::vector<Frame> completed_frames;

    // Pre-allocate for typical case (1-2 frames per batch)
    completed_frames.reserve(4);

    if (debug) {
        std::cerr << "[BATCH] Processing batch of " << batch_size << " packets" << std::endl;
    }

    // Process each packet in the batch
    for (size_t i = 0; i < batch_size; ++i) {
        try {
            auto result = add_packet(
                device_ts_ns_batch[i],
                xyz_data_batch[i],
                point_counts[i],
                seq_batch[i],
                debug
            );

            if (result.has_value()) {
                completed_frames.push_back(std::move(*result));
                if (debug) {
                    std::cerr << "[BATCH] Frame completed at packet " << i << std::endl;
                }
            }
        } catch (const std::exception& e) {
            if (debug) {
                std::cerr << "[BATCH] Error processing packet " << i
                         << ": " << e.what() << " (skipping)" << std::endl;
            }
            // Continue with next packet
        }
    }

    if (debug) {
        std::cerr << "[BATCH] Completed " << completed_frames.size()
                 << " frames from " << batch_size << " packets" << std::endl;
    }

    return completed_frames;
}

void FrameBuilder::reset() {
    current_point_count_ = 0;
    current_frame_start_ts_ = -1;
    current_frame_end_ts_ = -1;
    current_seq_first_ = 0;
    current_seq_last_ = 0;
    current_pkt_count_ = 0;
    last_seq_ = std::nullopt;
    point_buffer_.clear();
}

// ============================================================================
// Private helpers
// ============================================================================

void FrameBuilder::start_new_frame(int64_t device_ts_ns, uint32_t seq) {
    current_frame_start_ts_ = device_ts_ns;
    current_frame_end_ts_ = device_ts_ns;
    current_seq_first_ = seq;
    current_seq_last_ = seq;
    current_pkt_count_ = 0;
    current_point_count_ = 0;
    point_buffer_.clear();  // Clear previous data
}

void FrameBuilder::add_to_current_frame(
    int64_t device_ts_ns,
    const float* xyz_data,
    size_t point_count,
    uint32_t seq,
    bool debug)
{
    PROFILE_START();
    g_add_to_frame_calls++;

    // Sequence tracking (detect gaps and reorders)
    if (last_seq_.has_value()) {
        if (is_sequence_gap(seq, last_seq_.value())) {
            stats_.seq_gaps++;
            if (debug) {
                std::cerr << "[FRAME] Sequence gap: " << last_seq_.value()
                         << " -> " << seq << std::endl;
            }
        }
        if (is_sequence_reorder(seq, last_seq_.value())) {
            stats_.seq_reorders++;
            if (debug) {
                std::cerr << "[FRAME] Sequence reorder: " << last_seq_.value()
                         << " -> " << seq << std::endl;
            }
        }
    }
    last_seq_ = seq;

    // Check for overflow
    if (current_point_count_ + point_count > max_frame_points_) {
        stats_.overflow_frames++;
        if (debug) {
            std::cerr << "[FRAME] Overflow: " << current_point_count_
                     << " + " << point_count << " > " << max_frame_points_
                     << " (dropping packet, seq=" << seq << ")" << std::endl;
        }
        return;
    }

    // Copy points directly into buffer (zero-copy accumulation)
    const size_t offset = current_point_count_ * 3;
    const size_t bytes = point_count * 3 * sizeof(float);

    // Ensure buffer has enough space
    if (point_buffer_.size() < offset + point_count * 3) {
        point_buffer_.resize(offset + point_count * 3);
    }

    // Profile memcpy
    {
        auto memcpy_start = std::chrono::high_resolution_clock::now();
        std::memcpy(&point_buffer_[offset], xyz_data, bytes);
        auto memcpy_end = std::chrono::high_resolution_clock::now();
        auto memcpy_us = std::chrono::duration_cast<std::chrono::microseconds>(memcpy_end - memcpy_start).count();

        g_memcpy_calls++;
        g_memcpy_bytes += bytes;
        g_memcpy_total_us += memcpy_us;
    }

    // Update metadata
    current_point_count_ += point_count;
    current_frame_end_ts_ = device_ts_ns;
    current_seq_last_ = seq;
    current_pkt_count_++;

    // Update statistics
    stats_.packets_added++;
    stats_.points_added += point_count;

    PROFILE_END("add_to_frame", g_add_to_frame_total_us);
}

std::optional<Frame> FrameBuilder::close_current_frame(bool debug) {
    PROFILE_START();
    g_close_frame_calls++;

    if (current_point_count_ == 0) {
        if (debug) {
            std::cerr << "[FRAME] Empty frame, not closing" << std::endl;
        }
        return std::nullopt;
    }

    // Create frame object
    Frame frame;
    frame.point_count = current_point_count_;
    frame.start_ts_ns = current_frame_start_ts_;
    frame.end_ts_ns = current_frame_end_ts_;
    frame.seq_first = current_seq_first_;
    frame.seq_last = current_seq_last_;
    frame.pkt_count = current_pkt_count_;

    // Copy accumulated points (single copy at frame close)
    frame.xyz_data.resize(current_point_count_ * 3);

    // Profile frame close memcpy
    {
        auto memcpy_start = std::chrono::high_resolution_clock::now();
        const size_t bytes = current_point_count_ * 3 * sizeof(float);
        std::memcpy(frame.xyz_data.data(), point_buffer_.data(), bytes);
        auto memcpy_end = std::chrono::high_resolution_clock::now();
        auto memcpy_us = std::chrono::duration_cast<std::chrono::microseconds>(memcpy_end - memcpy_start).count();

        g_memcpy_calls++;
        g_memcpy_bytes += bytes;
        g_memcpy_total_us += memcpy_us;
    }

    // Update statistics
    stats_.frames_built++;

    if (debug) {
        std::cerr << "[FRAME] Closed: " << frame.repr() << std::endl;
    }

    // Reset for next frame
    current_point_count_ = 0;
    current_frame_start_ts_ = -1;

    PROFILE_END("close_frame", g_close_frame_total_us);
    return frame;
}

// Sequence tracking helpers
bool FrameBuilder::is_sequence_gap(uint32_t current_seq, uint32_t last_seq) const {
    // Allow wrap-around (uint32_t overflow)
    uint32_t expected = last_seq + 1;
    return (current_seq != expected) && (current_seq > last_seq);
}

bool FrameBuilder::is_sequence_reorder(uint32_t current_seq, uint32_t last_seq) const {
    // Detect backward sequence (reorder)
    return current_seq < last_seq && (last_seq - current_seq < 1000); // Not wrap-around
}

// ============================================================================
// Profiling statistics export
// ============================================================================

void print_profiling_stats() {
    std::cerr << "\n========================================\n";
    std::cerr << "Frame Builder C++ Profiling Statistics\n";
    std::cerr << "========================================\n";

    std::cerr << "Function Calls:\n";
    std::cerr << "  add_to_frame: " << g_add_to_frame_calls << " calls\n";
    std::cerr << "  close_frame: " << g_close_frame_calls << " calls\n";

    if (g_add_to_frame_calls > 0) {
        double avg_add = static_cast<double>(g_add_to_frame_total_us) / g_add_to_frame_calls;
        std::cerr << "  avg add_to_frame: " << avg_add << " μs/call\n";
    }

    if (g_close_frame_calls > 0) {
        double avg_close = static_cast<double>(g_close_frame_total_us) / g_close_frame_calls;
        std::cerr << "  avg close_frame: " << avg_close << " μs/call\n";
    }

    std::cerr << "\nmemcpy Statistics:\n";
    std::cerr << "  Total calls: " << g_memcpy_calls << "\n";
    std::cerr << "  Total bytes: " << g_memcpy_bytes << " ("
              << (g_memcpy_bytes / 1024.0 / 1024.0) << " MB)\n";
    std::cerr << "  Total time: " << g_memcpy_total_us << " μs\n";

    if (g_memcpy_calls > 0) {
        double avg_bytes = static_cast<double>(g_memcpy_bytes) / g_memcpy_calls;
        double avg_us = static_cast<double>(g_memcpy_total_us) / g_memcpy_calls;
        std::cerr << "  avg per call: " << avg_bytes << " bytes, " << avg_us << " μs\n";
    }

    std::cerr << "========================================\n\n";
}

} // namespace frame_builder

