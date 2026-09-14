#pragma once

#include "ingestion/session.hpp"
#include "persistence/sqlite_store.hpp"

namespace collector {
enum class ProcessState { Starting, Running, Stopped, Failed };
const char* ProcessStateName(ProcessState state);

// Owned by the main loop, and used only while DailyBarStore holds the directory writer lock.
class RuntimeStatusStore {
public:
    explicit RuntimeStatusStore(const std::filesystem::path& directory)
        : path_(directory / "collector-runtime.sqlite") {}
    bool Publish(const RuntimeSnapshot& snapshot, const DailyBarStore& market,
                 ProcessState state, std::int64_t heartbeat_us = NowUs());
private:
    const std::filesystem::path path_;
};
} // namespace collector
