#include "runtime.hpp"
#include "storage.hpp"
#include "health.hpp"
#include <thread>

namespace collector {
namespace {
void Report(const CtpSession& session, const MarketSnapshotBuffer& buffer, const DailyStore& store) {
    const auto status = session.Status();
    const auto stats = buffer.Stats();
    const auto now = NowUs();
    std::size_t subscribed = 0, failed = 0, receiving = 0;
    for (const auto& item : status.instruments) {
        const auto& value = item.second;
        subscribed += value.subscription == Subscription::Subscribed;
        failed += value.subscription == Subscription::Failed;
        const auto age = value.last_received_us ? (now - value.last_received_us) / 1000000 : -1;
        receiving += age >= 0 && age < 30;
        ctp::Log("utc_us=", now, " event=instrument_status run_id=", store.RunId(),
            " instrument=", item.first, " subscription=", SubscriptionName(value.subscription),
            " error_id=", value.error_id, " session_received=", value.received,
            " last_received_us=", value.last_received_us, " age_seconds=", age);
    }
    ctp::Log("utc_us=", now, " event=health run_id=", store.RunId(),
        " connected=", status.connected, " logged_in=", status.logged_in,
        " connections=", status.connections, " disconnections=", status.disconnections,
        " expected=", status.instruments.size(), " subscribed=", subscribed, " subscription_failed=", failed,
        " receiving_within_30s=", receiving, " accepted=", stats.accepted,
        " invalid_day=", stats.invalid_day, " unknown_instrument=", stats.unknown_instrument, " old_day=", stats.old_day,
        " last_received_us=", stats.last_received_us, " written=", store.Written(), " last_commit_us=", store.LastCommitUs());
}
} // namespace

int RunCollector(const Config& config, const volatile std::sig_atomic_t& stop, ApiPtr api) {
    const std::string source = api ? "TEST DOUBLE - injected API" : std::string("CTP ") + CThostFtdcMdApi::GetApiVersion();
    DailyStore store(config.data_directory, config.snapshot_interval_ms, config.instruments, source);
    MarketSnapshotBuffer buffer(config.instruments);
    std::filesystem::create_directories(config.flow_path);
    std::string flow_path = config.flow_path.string();
    if (flow_path.back() != '/') flow_path += '/';
    if (!api) api.reset(CThostFtdcMdApi::CreateFtdcMdApi(flow_path.c_str(), false, false, true));
    if (!api) throw std::runtime_error("CreateFtdcMdApi returned null");
    CtpSession session(*api, config, buffer, store.RunId());
    std::string front = config.front;
    const auto started_ms = SteadyMs();
    ctp::Log("utc_us=", NowUs(), " event=start run_id=", store.RunId(),
        " source=\"", source, "\" sqlite_version=", sqlite3_libversion(),
        " front=", front, " data_directory=", config.data_directory.string(), " snapshot_interval_ms=", config.snapshot_interval_ms);
    const auto release = [&] {
        if (api) { api->RegisterSpi(nullptr); api.reset(); }
    };
    const auto flush = [&] {
        const auto snapshots = buffer.Materialize(NowUs());
        if (snapshots.empty()) return;
        try {
            const auto inserted = store.Write(snapshots);
            ctp::Log("utc_us=", NowUs(), " event=snapshot_commit run_id=", store.RunId(),
                " rows=", inserted, " written=", store.Written(), " last_commit_us=", store.LastCommitUs());
        } catch (const std::exception& error) {
            ctp::Log("utc_us=", NowUs(), " event=persistence_failed run_id=", store.RunId(), " message=\"", error.what(), "\"");
            throw;
        }
    };
    const auto publish = [&](ProcessState state) {
        PublishHealth(config.data_directory, session.Status(), buffer.Stats(), store, state);
    };
    try {
        publish(ProcessState::Starting);
        api->RegisterSpi(&session); api->RegisterFront(front.data()); api->Init();
        auto next_snapshot_ms = started_ms + config.snapshot_interval_ms;
        auto next_status_ms = started_ms;
        auto next_heartbeat_ms = started_ms;
        std::int64_t logged_in_ms = -1;
        while (!stop) {
            const auto now_ms = SteadyMs();
            session.Pump(now_ms);
            if (logged_in_ms < 0 && session.HasLoggedIn()) logged_in_ms = now_ms;
            if (now_ms >= next_heartbeat_ms) {
                publish(logged_in_ms < 0 ? ProcessState::Starting : ProcessState::Running);
                next_heartbeat_ms = now_ms + 2000;
            }
            if (now_ms >= next_snapshot_ms) {
                flush(); next_snapshot_ms = SteadyMs() + config.snapshot_interval_ms;
            }
            if (now_ms >= next_status_ms) {
                Report(session, buffer, store); next_status_ms = now_ms + config.status_interval_seconds * 1000;
            }
            if (logged_in_ms < 0 && now_ms - started_ms >= config.connect_timeout_seconds * 1000)
                throw std::runtime_error("startup connection/login timeout");
            if (config.run_seconds > 0 && logged_in_ms >= 0 && now_ms - logged_in_ms >= static_cast<std::int64_t>(config.run_seconds) * 1000) break;
            std::this_thread::sleep_for(std::chrono::milliseconds(20));
        }
        // The SPI and MarketSnapshotBuffer outlive Release, including any callbacks already in flight.
        release(); session.CheckFailure(); flush(); Report(session, buffer, store);
        try { store.Finish(); }
        catch (const std::exception& error) {
            ctp::Log("utc_us=", NowUs(), " event=persistence_failed run_id=", store.RunId(), " message=\"", error.what(), "\"");
            throw;
        }
        publish(ProcessState::Stopped);
        ctp::Log("utc_us=", NowUs(), " event=stop run_id=", store.RunId(), " reason=", stop ? "signal" : "run_window_complete",
            " written=", store.Written());
        return 0;
    } catch (...) {
        release();
        publish(ProcessState::Failed);
        ctp::Log("utc_us=", NowUs(), " event=collector_failed run_id=", store.RunId(), " written=", store.Written());
        throw;
    }
}
} // namespace collector
