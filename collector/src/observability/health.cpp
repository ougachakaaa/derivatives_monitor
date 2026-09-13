#include "observability/health.hpp"

#include <fstream>
#include <sstream>

namespace collector {

const char* ProcessStateName(ProcessState state) {
    switch (state) {
        case ProcessState::Starting: return "starting";
        case ProcessState::Running: return "running";
        case ProcessState::Stopped: return "stopped";
        case ProcessState::Failed: return "failed";
    }
    return "failed";
}

bool PublishHealth(const std::filesystem::path& directory, const SessionStatus& session,
                   const AggregationStats& aggregation, const DailyBarStore& store, ProcessState state) {
    const auto temporary = directory / ".collector-status.tmp";
    const auto coverage_temporary = directory / ".collector-coverage.tmp";
    try {
        std::size_t subscribed = 0, failed = 0;
        for (const auto& item : session.instruments) {
            subscribed += item.second.subscription == Subscription::Subscribed;
            failed += item.second.subscription == Subscription::Failed;
        }
        const bool alive = state == ProcessState::Starting || state == ProcessState::Running;
        const auto updated_us = NowUs();
        std::ostringstream json;
        json << std::boolalpha
             << "{\n  \"schema_version\": 2,\n  \"run_id\": \"" << store.RunId()
             << "\",\n  \"updated_us\": " << updated_us
             << ",\n  \"process_state\": \"" << ProcessStateName(state)
             << "\",\n  \"connected\": " << (alive && session.connected)
             << ",\n  \"logged_in\": " << (alive && session.logged_in)
             << ",\n  \"connections\": " << session.connections
             << ",\n  \"disconnections\": " << session.disconnections
             << ",\n  \"expected\": " << session.instruments.size()
             << ",\n  \"subscribed\": " << subscribed
             << ",\n  \"subscription_failed\": " << failed
             << ",\n  \"callbacks_accepted\": " << aggregation.callbacks_accepted
             << ",\n  \"bars_written\": " << store.BarsWritten()
             << ",\n  \"partial_bars\": " << store.PartialBars()
             << ",\n  \"late_callbacks\": " << aggregation.late_callbacks
             << ",\n  \"invalid_trading_day\": " << aggregation.invalid_trading_day
             << ",\n  \"invalid_event_time\": " << aggregation.invalid_event_time
             << ",\n  \"last_received_us\": " << aggregation.last_received_us
             << ",\n  \"last_commit_us\": " << store.LastCommitUs() << "\n}\n";
        std::ofstream output(temporary, std::ios::trunc);
        output << json.str();
        output.close();
        if (!output) throw std::runtime_error("cannot write diagnostic heartbeat");
        std::filesystem::rename(temporary, directory / ".collector-status.json");

        std::ofstream coverage(coverage_temporary, std::ios::trunc);
        coverage << "{\"schema_version\":2,\"run_id\":\"" << store.RunId()
                 << "\",\"updated_us\":" << updated_us << ",\"instruments\":[";
        bool first = true;
        for (const auto& item : session.instruments) {
            if (!first) coverage << ',';
            first = false;
            const auto aggregation_it = aggregation.instruments.find(item.first);
            const auto store_it = store.InstrumentStats().find(item.first);
            const InstrumentAggregationStats empty_aggregation{};
            const InstrumentStoreStats empty_store{};
            const auto& a = aggregation_it == aggregation.instruments.end() ? empty_aggregation : aggregation_it->second;
            const auto& s = store_it == store.InstrumentStats().end() ? empty_store : store_it->second;
            coverage << "{\"id\":\"" << item.first << "\",\"subscription\":\""
                     << SubscriptionName(item.second.subscription) << "\",\"error_id\":" << item.second.error_id
                     << ",\"callbacks_accepted\":" << a.callbacks_accepted
                     << ",\"last_received_us\":" << a.last_received_us
                     << ",\"bars_written\":" << s.bars_written
                     << ",\"partial_bars\":" << s.partial_bars
                     << ",\"late_callbacks\":" << a.late_callbacks << '}';
        }
        coverage << "]}\n";
        coverage.close();
        if (!coverage) throw std::runtime_error("cannot write coverage diagnostic");
        std::filesystem::rename(coverage_temporary, directory / ".collector-coverage.json");
        return true;
    } catch (const std::exception& error) {
        std::error_code ignored;
        std::filesystem::remove(temporary, ignored);
        std::filesystem::remove(coverage_temporary, ignored);
        ctp::Log("event=status_write_failed run_id=", store.RunId(), " message=\"", error.what(), "\"");
        return false;
    }
}

} // namespace collector
