#pragma once
#include "market.hpp"
#include <sqlite3.h>

namespace collector {
class DailyStore {
public:
    DailyStore(std::filesystem::path directory, int interval_ms, const std::vector<std::string>& instruments);
    ~DailyStore();
    DailyStore(const DailyStore&) = delete;
    DailyStore& operator=(const DailyStore&) = delete;
    std::uint64_t Write(const std::vector<Snapshot>& snapshots);
    void Finish();
    const std::string& RunId() const { return run_id_; }
    std::uint64_t Written() const { return written_; }
    std::int64_t LastCommitUs() const { return last_commit_us_; }
private:
    void Open(const std::string& day);
    void Close() noexcept;
    std::filesystem::path directory_;
    int lock_fd_ = -1;
    sqlite3* db_ = nullptr;
    std::string day_, run_id_, instruments_;
    int interval_ms_;
    const std::int64_t started_us_ = NowUs();
    std::set<std::string> touched_days_;
    std::uint64_t written_ = 0;
    std::int64_t last_commit_us_ = 0;
};
} // namespace collector
