// MMQ row tables need space for full-tile reads beyond the logical rows.
#pragma once

#include <cstddef>
#include <cstdint>
#include <limits>

namespace strata::prefill::mmq {

// Must match the J dispatcher in the pinned ggml MMQ and moe_mmq_tab.cuh.
constexpr int kMmqTileColsMin = 8;
constexpr int kMmqTileColsMax = 128;
constexpr int kMmqTileColsStep = 8;

inline bool mmq_ids_margin_rows(int64_t max_rows, int tile_cols_max, int64_t* out) {
    if (max_rows < 0 || tile_cols_max <= 0 || out == nullptr) return false;
    const int64_t J = tile_cols_max;
    const int64_t tiles = max_rows / J + (max_rows % J != 0 ? 1 : 0);
    if (tiles > INT64_MAX / J) return false;
    const int64_t rounded = tiles * J;
    if (rounded > INT64_MAX - J) return false;
    *out = rounded + J;
    return true;
}

// Zero means invalid or too large for int32 IDs and aligned allocations. The kernel computes
// col_low + jt*J + j in int: bounds[n] + margin <= INT32_MAX keeps that arithmetic in range.
inline uint64_t mmq_ids_table_rows(uint64_t rows, uint64_t max_rows, int tile_cols_max = kMmqTileColsMax) {
    int64_t margin = 0;
    if (max_rows > (uint64_t) INT64_MAX || !mmq_ids_margin_rows((int64_t) max_rows, tile_cols_max, &margin)) return 0;
    constexpr uint64_t id_limit = (uint64_t) std::numeric_limits<int32_t>::max();
    constexpr uint64_t size_limit = ((uint64_t) std::numeric_limits<size_t>::max() - 255) / sizeof(int32_t); // 256-byte alignment
    constexpr uint64_t limit = id_limit < size_limit ? id_limit : size_limit;
    if ((uint64_t) margin > limit || rows > limit - (uint64_t) margin) return 0;
    return rows + (uint64_t) margin;
}

inline uint64_t mmq_prompt_ids_table_rows(uint64_t tokens, uint64_t experts_per_token) {
    if (experts_per_token == 0 || tokens > UINT64_MAX / experts_per_token) return 0;
    const uint64_t rows = tokens * experts_per_token;
    // A product's bounds can reach the whole row space, and a launch's max_rows is an expert's
    // row count - <= tokens under distinct-per-token routing. Margining for `rows` keeps the
    // bound independent of that routing invariant (a single entry owning the row space).
    return mmq_ids_table_rows(rows, rows);
}

}  // namespace strata::prefill::mmq
