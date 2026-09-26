#pragma once

#include <atomic>
#include <cstddef>
#include <vector>

// Single-producer single-consumer float ring buffer: the audio callback writes, a Kotlin thread reads.
class RingBuffer {
public:
    explicit RingBuffer(size_t capacity) : data_(capacity + 1) {}

    // Returns the number of samples written; drops what does not fit.
    size_t write(const float* src, size_t n) {
        const size_t w = write_.load(std::memory_order_relaxed);
        const size_t r = read_.load(std::memory_order_acquire);
        const size_t cap = data_.size();
        const size_t free = (r + cap - w - 1) % cap;
        const size_t count = n < free ? n : free;
        for (size_t i = 0; i < count; ++i) data_[(w + i) % cap] = src[i];
        write_.store((w + count) % cap, std::memory_order_release);
        return count;
    }

    size_t read(float* dst, size_t n) {
        const size_t r = read_.load(std::memory_order_relaxed);
        const size_t w = write_.load(std::memory_order_acquire);
        const size_t cap = data_.size();
        const size_t avail = (w + cap - r) % cap;
        const size_t count = n < avail ? n : avail;
        for (size_t i = 0; i < count; ++i) dst[i] = data_[(r + i) % cap];
        read_.store((r + count) % cap, std::memory_order_release);
        return count;
    }

    void clear() { read_.store(write_.load()); }

private:
    std::vector<float> data_;
    std::atomic<size_t> write_{0};
    std::atomic<size_t> read_{0};
};
