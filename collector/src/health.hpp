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
    const auto coverage_temporary = directory / ".collector-coverage.tmp";
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
        // Kept separate so the small heartbeat remains bounded for existing readers.
        std::ofstream coverage(coverage_temporary, std::ios::trunc);
        coverage << "{\"schema_version\":1,\"run_id\":\"" << store.RunId()
                 << "\",\"updated_us\":" << NowUs() << ",\"instruments\":[";
        bool first = true;
        for (const auto& item : session.instruments) {
            if (!first) coverage << ',';
            first = false;
            // Instrument IDs have already passed the restricted ASCII config validation.
            coverage << "{\"id\":\"" << item.first << "\",\"subscription\":\""
                     << SubscriptionName(item.second.subscription) << "\",\"error_id\":" << item.second.error_id
                     << ",\"received\":" << item.second.received
                     << ",\"last_received_us\":" << item.second.last_received_us << '}';
        }
        coverage << "]}\n"; coverage.close();
        if (!coverage) throw std::runtime_error("cannot write coverage diagnostic");
        std::filesystem::rename(coverage_temporary, directory / ".collector-coverage.json");
        return true;
    } catch (const std::exception& error) {
        std::error_code ignored; std::filesystem::remove(temporary, ignored);
        std::filesystem::remove(coverage_temporary, ignored);
        ctp::Log("event=status_write_failed run_id=", store.RunId(), " message=\"", error.what(), "\"");
        return false;
    }
}
} // namespace collector
