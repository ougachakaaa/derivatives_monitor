#pragma once

#include "domain/market.hpp"

#include <sqlite3.h>

#include <filesystem>
#include <map>
#include <set>

namespace collector {

struct InstrumentStoreStats {
    std::uint64_t bars_written = 0;
    std::uint64_t partial_bars = 0;
};

class DailyBarStore {
public:
    DailyBarStore(std::filesystem::path directory, const std::vector<std::string>& instruments, std::string source);
    ~DailyBarStore();
    DailyBarStore(const DailyBarStore&) = delete;
    DailyBarStore& operator=(const DailyBarStore&) = delete;

    std::uint64_t Write(const std::vector<MarketBar>& bars);
    void Finish();
    const std::string& RunId() const { return run_id_; }
    std::uint64_t BarsWritten() const { return bars_written_; }
    std::uint64_t PartialBars() const { return partial_bars_; }
    std::int64_t LastCommitUs() const { return last_commit_us_; }
    const std::map<std::string, InstrumentStoreStats>& InstrumentStats() const { return instrument_stats_; }

private:
    void Open(const std::string& day);
    void Close() noexcept;
    std::filesystem::path directory_;
    int lock_fd_ = -1;
    sqlite3* db_ = nullptr;
    std::string day_, run_id_, instruments_, source_;
    const std::int64_t started_us_ = NowUs();
    std::set<std::string> touched_days_;
    std::map<std::string, InstrumentStoreStats> instrument_stats_;
    std::uint64_t bars_written_ = 0, partial_bars_ = 0;
    std::int64_t last_commit_us_ = 0;
};

} // namespace collector
