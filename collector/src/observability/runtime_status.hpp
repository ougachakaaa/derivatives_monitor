#pragma once

#include "ingestion/session.hpp"
#include "persistence/sqlite_store.hpp"

#include <set>
#include <vector>

namespace collector {
enum class ProcessState { Starting, Running, Stopped, Failed };
const char* ProcessStateName(ProcessState state);

// Owned by the main loop, and used only while DailyBarStore holds the directory writer lock.
class RuntimeStatusStore {
public:
    explicit RuntimeStatusStore(const std::filesystem::path& directory)
        : path_(directory / "collector-runtime.sqlite") {}
    bool StartRun(const DailyBarStore& market);
    bool Publish(const RuntimeSnapshot& snapshot, const DailyBarStore& market,
                 ProcessState state, std::int64_t heartbeat_us = NowUs());
    std::int64_t CurrentIntervalStartUs() const { return current_interval_start_us_; }
private:
    struct HistoryRow {
        std::int64_t interval_start_us = 0, interval_end_us = 0, observed_us = 0;
        ProcessState state = ProcessState::Starting;
        bool connected = false, logged_in = false;
        std::uint64_t target_count = 0, subscribed_count = 0, subscription_failed = 0;
        std::uint64_t tick_count = 0, market_bar_count = 0, partial_bar_count = 0;
        std::int64_t last_tick_received_us = 0, last_market_commit_us = 0;
    };
    void Observe(const RuntimeSnapshot& snapshot, const DailyBarStore& market,
                 ProcessState state, std::int64_t now_us);
    static std::int64_t CeilingBoundary(std::int64_t now_us);
    const std::filesystem::path path_;
    bool started_ = false;
    ProcessState last_active_state_ = ProcessState::Starting;
    std::int64_t current_interval_start_us_ = 0, last_wall_us_ = 0;
    std::vector<HistoryRow> pending_;
    std::set<std::int64_t> used_intervals_;
};
} // namespace collector
