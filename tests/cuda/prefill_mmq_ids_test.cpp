// Synthetic Layer-Major MMQ row-table regression. No model or network is needed.
#include "strata/prefill/moe_mmq.hpp"

#include "ggml.h"
#include <cuda_runtime.h>

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
namespace mmq = strata::prefill::mmq;
constexpr int kTokens = 100, kExpertsPerToken = 10, kRows = kTokens * kExpertsPerToken;
constexpr int kCols = 2560, kOut = 128, kExperts = 2;

void ck(cudaError_t e, const char* what) {
    if (e != cudaSuccess) throw std::runtime_error(std::string(what) + ": " + cudaGetErrorString(e));
}

struct Dev {
    void* p = nullptr;
    explicit Dev(size_t bytes) { ck(cudaMalloc(&p, bytes), "cudaMalloc"); }
    ~Dev() { cudaFree(p); }
    Dev(const Dev&) = delete;
    Dev& operator=(const Dev&) = delete;
};

void run(size_t ids_rows) {
    const size_t expert_bytes = mmq::matrix_bytes(GGML_TYPE_Q8_0, kOut, kCols);
    const size_t row_bytes = ggml_row_size(GGML_TYPE_Q8_0, kCols);
    if (expert_bytes != row_bytes * kOut) throw std::runtime_error("weight geometry");
    const auto* traits = ggml_get_type_traits(GGML_TYPE_Q8_0);
    if (!traits || !traits->from_float_ref) throw std::runtime_error("missing Q8_0 reference quantizer");

    std::vector<uint8_t> weights(kExperts * expert_bytes + 4096, 0);
    std::vector<float> row(kCols);
    for (int e = 0; e < kExperts; ++e) {
        std::fill(row.begin(), row.end(), e == 0 ? 1.0f : 0.5f);
        for (int r = 0; r < kOut; ++r)
            traits->from_float_ref(row.data(), weights.data() + e * expert_bytes + r * row_bytes, kCols);
    }
    std::vector<float> x((size_t) kRows * kCols);
    for (int r = 0; r < kRows; ++r)
        std::fill(x.begin() + (size_t) r * kCols, x.begin() + (size_t) (r + 1) * kCols, 0.5f + 0.1f * (r % 7));
    const int32_t bounds[kExperts + 1] = {0, kRows - 1, kRows};
    const size_t out_bytes = (size_t) kRows * kOut * sizeof(float);
    Dev dw(weights.size()), dx(x.size() * sizeof(float)), dxq(mmq::q8_bytes(kRows, kCols));
    Dev db(sizeof(bounds)), dids(ids_rows * sizeof(int32_t)), dy(out_bytes);
    ck(cudaMemcpy(dw.p, weights.data(), weights.size(), cudaMemcpyHostToDevice), "weights");
    ck(cudaMemcpy(dx.p, x.data(), x.size() * sizeof(float), cudaMemcpyHostToDevice), "activations");
    ck(cudaMemcpy(db.p, bounds, sizeof(bounds), cudaMemcpyHostToDevice), "bounds");
    ck(cudaMemset(dy.p, 0xff, out_bytes), "output sentinel");
    ck(cudaDeviceSynchronize(), "inputs");

    cudaStream_t stream = nullptr;
    ck(cudaStreamCreateWithFlags(&stream, cudaStreamNonBlocking), "stream");
    {
        mmq::Context ctx;
        mmq::iota((int32_t*) dids.p, (int64_t) ids_rows, stream);
        mmq::quantize((const float*) dx.p, nullptr, dxq.p, GGML_TYPE_Q8_0, kCols, kCols, kRows, stream);
        mmq::Product p;
        p.w = dw.p; p.type = GGML_TYPE_Q8_0; p.w_rows = kOut; p.w_cols = kCols; p.expert_bytes = expert_bytes;
        p.n = kExperts; p.xq = dxq.p; p.bounds = (const int32_t*) db.p; p.ids = (const int32_t*) dids.p;
        p.total_rows = kRows; p.max_rows = kRows - 1; p.dst = (float*) dy.p; p.ld_dst = kOut;
        ctx.run(p, stream);
        ck(cudaGetLastError(), "launch");
        ck(cudaStreamSynchronize(stream), "MMQ");
    }
    ck(cudaStreamDestroy(stream), "destroy stream");
    std::vector<float> out((size_t) kRows * kOut);
    ck(cudaMemcpy(out.data(), dy.p, out_bytes, cudaMemcpyDeviceToHost), "result");
    for (int r = 0; r < kRows; ++r) {
        const float expected = (0.5f + 0.1f * (r % 7)) * kCols * (r == kRows - 1 ? 0.5f : 1.0f);
        for (int c = 0; c < kOut; ++c) {
            const float actual = out[(size_t) r * kOut + c];
            if (!std::isfinite(actual) || std::fabs(actual - expected) > 0.02f * expected)
                throw std::runtime_error("MMQ result differs from the constant-weight reference");
        }
    }
}
}  // namespace

int main(int argc, char** argv) {
    try {
        // --unsafe-* deliberately under-size the row table: their verdict is the
        // compute-sanitizer output; a garbage read may also fail the result check (exit 1).
        size_t ids_rows = (size_t) mmq::mmq_prompt_ids_table_rows(kTokens, kExpertsPerToken);
        const char* mode = "padded";
        if (argc == 2 && std::string(argv[1]) == "--unsafe-exact-ids") {
            ids_rows = kRows;
            mode = "unsafe exact-size negative control";
        } else if (argc == 2 && std::string(argv[1]) == "--unsafe-upstream-margin") {
            ids_rows = (size_t) mmq::mmq_ids_table_rows(kRows, kTokens);
            mode = "unsafe upstream-margin negative control";
        } else if (argc != 1) {
            std::fprintf(stderr, "usage: %s [--unsafe-exact-ids|--unsafe-upstream-margin]\n", argv[0]);
            return 2;
        }
        int count = 0;
        if (cudaGetDeviceCount(&count) != cudaSuccess || count == 0) {
            std::puts("no CUDA device: skipped");
            return 77;
        }
        if (ids_rows == 0 || !mmq::built() || !mmq::fits(GGML_TYPE_Q8_0, kOut)) {
            std::puts("Q8_0 MMQ unavailable: skipped");
            return 77;
        }
        std::printf("MMQ row-table test: %s, %zu entries\n", mode, ids_rows);
        run(ids_rows);
        std::puts("MMQ numerical reference passed; use compute-sanitizer to check memory accesses");
        return 0;
    } catch (const std::exception& e) {
        std::fprintf(stderr, "MMQ row-table test failed: %s\n", e.what());
        return 1;
    }
}
