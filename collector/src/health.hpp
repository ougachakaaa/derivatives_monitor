#pragma once
#include "session.hpp"
#include "storage.hpp"
#include <sstream>

namespace collector {
enum class ProcessState { Starting, Running, Stopped, Failed };
inline const char* ProcessStateName(ProcessState state) {
    switch (state) {
        case ProcessState::Starting: return "starting";
        case ProcessState::Running: return "running";
        case ProcessState::Stopped: return "stopped";
        case ProcessState::Failed: return "failed";
    }
    return "failed";
}

// Diagnostic only: failure must never make the ingestion path depend on its reader.
inline bool PublishHealth(const std::filesystem::path& directory, const SessionStatus& session,
                          const StateStats& market, const DailyStore& store, ProcessState state) {
    const auto temporary = directory / ".collector-status.tmp";
    try {
        std::size_t subscribed = 0, failed = 0;
        for (const auto& item : session.instruments) {
            subscribed += item.second.subscription == Subscription::Subscribed;
            failed += item.second.subscription == Subscription::Failed;
        }
        const bool alive = state == ProcessState::Starting || state == ProcessState::Running;
        std::ostringstream json;
        // All strings here are fixed enum labels or the Collector-generated hex run ID.
        json << std::boolalpha
             << "{\n  \"schema_version\": 1,\n  \"run_id\": \"" << store.RunId()
             << "\",\n  \"updated_us\": " << NowUs()
             << ",\n  \"process_state\": \"" << ProcessStateName(state)
             << "\",\n  \"connected\": " << (alive && session.connected)
             << ",\n  \"logged_in\": " << (alive && session.logged_in)
             << ",\n  \"connections\": " << session.connections
             << ",\n  \"disconnections\": " << session.disconnections
             << ",\n  \"expected\": " << session.instruments.size()
             << ",\n  \"subscribed\": " << subscribed
             << ",\n  \"subscription_failed\": " << failed
             << ",\n  \"accepted\": " << market.accepted
             << ",\n  \"written\": " << store.Written()
             << ",\n  \"last_received_us\": " << market.last_received_us
             << ",\n  \"last_commit_us\": " << store.LastCommitUs() << "\n}\n";
        std::ofstream output(temporary, std::ios::trunc);
        output << json.str(); output.close();
        if (!output) throw std::runtime_error("cannot write diagnostic heartbeat");
        std::filesystem::rename(temporary, directory / ".collector-status.json");
        return true;
    } catch (const std::exception& error) {
        std::error_code ignored; std::filesystem::remove(temporary, ignored);
        ctp::Log("event=status_write_failed run_id=", store.RunId(), " message=\"", error.what(), "\"");
        return false;
    }
}
} // namespace collector
