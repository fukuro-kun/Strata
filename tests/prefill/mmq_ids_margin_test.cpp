// CPU model of the MMQ kernel's row-table bounds.
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <limits>
#include <random>
#include <vector>

#include "strata/prefill/mmq_ids_margin.hpp"

using namespace strata::prefill::mmq;

static int failed = 0;
#define CHECK(x) do { if (!(x)) { std::fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #x); ++failed; } } while (0)

static int64_t fixup_read_end(const std::vector<int64_t>& bounds, int64_t max_rows, int J) {
    const int64_t tiles = (max_rows + J - 1) / J;
    int64_t end = 0;
    for (size_t e = 0; e + 1 < bounds.size(); ++e)
        end = std::max(end, bounds[e] + tiles * J);
    return end;
}

static int64_t main_read_end(const std::vector<int64_t>& bounds, int J) {
    int64_t end = 0;
    for (size_t e = 0; e + 1 < bounds.size(); ++e)
        if (bounds[e + 1] > bounds[e]) end = std::max(end, bounds[e + 1] + J - 1);
    return end;
}

int main() {
    CHECK(kMmqTileColsMax == 128 && kMmqTileColsStep == 8);

    int64_t m = -1;
    CHECK(mmq_ids_margin_rows(0, 128, &m) && m == 128);
    CHECK(mmq_ids_margin_rows(1, 128, &m) && m == 256);
    CHECK(mmq_ids_margin_rows(128, 128, &m) && m == 256);
    CHECK(mmq_ids_margin_rows(129, 128, &m) && m == 384);
    CHECK(mmq_ids_margin_rows(3072, 128, &m) && m == 3200);
    CHECK(mmq_ids_margin_rows(3072, 8, &m) && m == 3080);
    CHECK(mmq_ids_table_rows(30720, 3072) == 30720 + 3200);
    CHECK(mmq_ids_table_rows(0, 0) == 128);

    m = 77;
    CHECK(!mmq_ids_margin_rows(-1, 128, &m) && m == 77);
    CHECK(!mmq_ids_margin_rows(10, 0, &m) && !mmq_ids_margin_rows(10, -8, &m));
    CHECK(!mmq_ids_margin_rows(10, 128, nullptr));
    CHECK(!mmq_ids_margin_rows(INT64_MAX, 128, &m));
    CHECK(!mmq_ids_margin_rows(INT64_MAX - 100, 128, &m));
    CHECK(mmq_ids_table_rows(UINT64_MAX - 5, 10) == 0);
    CHECK(mmq_ids_table_rows(10, (uint64_t) INT64_MAX + 1) == 0);
    CHECK(mmq_ids_table_rows(UINT64_MAX, 0) == 0);
    const uint64_t limit = std::min<uint64_t>(INT32_MAX, ((uint64_t) std::numeric_limits<size_t>::max() - 255) / sizeof(int32_t));
    CHECK(mmq_ids_table_rows(limit - 256, 1) == limit);
    CHECK(mmq_ids_table_rows(limit - 255, 1) == 0);
    CHECK(mmq_ids_table_rows(1, limit) == 0);
    CHECK(mmq_prompt_ids_table_rows(UINT64_MAX, 2) == 0);
    CHECK(mmq_prompt_ids_table_rows(10, 0) == 0);

    const int64_t K = 10;
    std::mt19937_64 rng(5108);
    for (int iter = 0; iter < 2000; ++iter) {
        const int64_t T = 1 + (int64_t) (rng() % (iter < 1000 ? 70 : 4096));
        const int NE = 1 + (int) (rng() % 64);
        std::vector<int64_t> cnt((size_t) NE, 0);
        int64_t left = T * K, widest = 0;
        for (int e = 0; e < NE && left > 0; ++e) {
            const int64_t c = std::min<int64_t>({(int64_t) (rng() % ((uint64_t) T + 1)), T, left});
            cnt[(size_t) e] = c;
            left -= c;
        }
        for (int e = 0; e < NE && left > 0; ++e) {
            const int64_t room = T - cnt[(size_t) e], c = std::min(room, left);
            cnt[(size_t) e] += c;
            left -= c;
        }
        std::vector<int64_t> bounds{0};
        int64_t total = 0;
        for (int64_t c : cnt) { total += c; bounds.push_back(total); widest = std::max(widest, c); }
        CHECK(widest <= T);
        const int64_t table = (int64_t) mmq_ids_table_rows((uint64_t) total, (uint64_t) T);
        for (int J = kMmqTileColsStep; J <= kMmqTileColsMax; J += kMmqTileColsStep) {
            CHECK(fixup_read_end(bounds, widest, J) <= table);
            CHECK(fixup_read_end(bounds, T, J) <= table);
            CHECK(main_read_end(bounds, J) <= table);
        }
    }

    const std::vector<int64_t> late{0, 100, 200, 200, 200};
    CHECK(fixup_read_end(late, 100, 128) > 200);
    CHECK(fixup_read_end(late, 100, 128) <= (int64_t) mmq_ids_table_rows(200, 100));

    // In a Layer-Major superchunk, one expert can have nearly T*K rows.
    const std::vector<int64_t> superchunk{0, 999, 1000};
    CHECK(fixup_read_end(superchunk, 999, 128) > (int64_t) mmq_ids_table_rows(1000, 100));
    CHECK(fixup_read_end(superchunk, 999, 128) <= (int64_t) mmq_prompt_ids_table_rows(100, 10));
    for (int64_t tokens = 1; tokens <= 200; ++tokens) {
        const int64_t rows = tokens * K;
        const std::vector<int64_t> late_group{0, rows - 1, rows};
        const int64_t table = (int64_t) mmq_prompt_ids_table_rows((uint64_t) tokens, (uint64_t) K);
        for (int J = kMmqTileColsStep; J <= kMmqTileColsMax; J += kMmqTileColsStep)
            CHECK(fixup_read_end(late_group, rows - 1, J) <= table);
    }

    if (failed) { std::fprintf(stderr, "%d check(s) failed\n", failed); return 1; }
    std::puts("mmq_ids_margin_test: ok");
    return 0;
}
