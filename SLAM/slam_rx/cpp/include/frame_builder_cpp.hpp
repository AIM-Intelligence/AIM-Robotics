#ifndef FRAME_BUILDER_CPP_HPP
#define FRAME_BUILDER_CPP_HPP

#include <vector>
#include <cstdint>
#include <string>
#include <optional>

// Frame Builder - Time-based Point Cloud Accumulator
//
// Accumulates LiDAR packets into frames based on device timestamps.
// Frames are closed when time window expires (frame_period_ns).
//
// Key optimization: Pre-allocated buffer eliminates np.vstack overhead

namespace frame_builder {

// Forward declarations
struct Frame;
struct FrameBuilderStats;
class FrameBuilder;

// ============================================================================
// Frame - Point cloud frame with metadata
// ============================================================================

struct Frame {
    std::vector<float> xyz_data;    // Flat array: [x0,y0,z0, x1,y1,z1, ...]
    size_t point_count;             // Number of points

    int64_t start_ts_ns;            // Frame start timestamp (nanoseconds)
    int64_t end_ts_ns;              // Frame end timestamp (nanoseconds)

    uint32_t seq_first;             // First packet sequence number
    uint32_t seq_last;              // Last packet sequence number

    uint32_t pkt_count;             // Number of packets in frame

    // Helper: frame duration in seconds
    double duration_s() const {
        return (end_ts_ns - start_ts_ns) / 1e9;
    }

    // String representation
    std::string repr() const;
};

// ============================================================================
// FrameBuilderStats - Statistics tracking
// ============================================================================

struct FrameBuilderStats {
    uint64_t frames_built = 0;      // Total frames built
    uint64_t packets_added = 0;     // Total packets added
    uint64_t points_added = 0;      // Total points added

    uint64_t late_packets = 0;      // Packets with ts < current_frame_start
    uint64_t seq_gaps = 0;          // Detected sequence gaps
    uint64_t seq_reorders = 0;      // Out-of-order packets
    uint64_t overflow_frames = 0;   // Frames exceeding max_frame_points

    // Reset all counters
    void reset();

    // String representation
    std::string repr() const;
};

// ============================================================================
// FrameBuilder - Time-based frame accumulator
// ============================================================================

class FrameBuilder {
public:
    // Constructor
    FrameBuilder(double frame_period_s,
                 size_t max_frame_points,
                 FrameBuilderStats& stats);

    // Destructor
    ~FrameBuilder() = default;

    // Add packet to current frame
    // Returns completed frame if time window expired, otherwise nullptr
    std::optional<Frame> add_packet(
        int64_t device_ts_ns,
        const float* xyz_data,
        size_t point_count,
        uint32_t seq,
        bool debug = false
    );

    // Add batch of packets (returns all completed frames)
    std::vector<Frame> add_packets_batch(
        const int64_t* device_ts_ns_batch,
        const float* const* xyz_data_batch,
        const size_t* point_counts,
        const uint32_t* seq_batch,
        size_t batch_size,
        bool debug = false
    );

    // Flush remaining frame (on shutdown)
    std::optional<Frame> flush(bool debug = false);

    // Reset state
    void reset();

    // Get statistics (const reference to avoid copies)
    const FrameBuilderStats& stats() const { return stats_; }

private:
    // Configuration
    int64_t frame_period_ns_;       // Frame period in nanoseconds
    size_t max_frame_points_;       // Maximum points per frame

    // Statistics reference (shared with Python)
    FrameBuilderStats& stats_;

    // Current frame state
    std::vector<float> point_buffer_;   // Pre-allocated buffer (max_frame_points * 3)
    size_t current_point_count_;        // Current fill level

    int64_t current_frame_start_ts_;    // Frame start timestamp (-1 if no frame)
    int64_t current_frame_end_ts_;      // Frame end timestamp

    uint32_t current_seq_first_;        // First packet sequence
    uint32_t current_seq_last_;         // Last packet sequence
    uint32_t current_pkt_count_;        // Packet counter

    std::optional<uint32_t> last_seq_;  // Last seen sequence (for gap detection)

    // Internal helpers
    std::optional<Frame> close_current_frame(bool debug);
    void add_to_current_frame(
        int64_t device_ts_ns,
        const float* xyz_data,
        size_t point_count,
        uint32_t seq,
        bool debug
    );
    void start_new_frame(int64_t device_ts_ns, uint32_t seq);

    // Sequence tracking helpers
    bool is_sequence_gap(uint32_t current_seq, uint32_t last_seq) const;
    bool is_sequence_reorder(uint32_t current_seq, uint32_t last_seq) const;
};

// Profiling utilities
void print_profiling_stats();

} // namespace frame_builder

#endif // FRAME_BUILDER_CPP_HPP
