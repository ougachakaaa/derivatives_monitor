#include "app/runtime.hpp"

#include "observability/runtime_status.hpp"
#include "persistence/sqlite_store.hpp"

#include <thread>

namespace collector {
namespace {

void Report(const CtpSession& session, const DailyBarStore& store) {
    const auto snapshot = session.Snapshot();
    const auto& status = snapshot.session;
    const auto& stats = snapshot.aggregation;
    const auto now = NowUs();
    std::size_t subscribed = 0, failed = 0, receiving = 0;
    for (const auto& item : status.instruments) {
        const auto& value = item.second;
        subscribed += value.subscription == Subscription::Subscribed;
        failed += value.subscription == Subscription::Failed;
        const auto facts_it = stats.instruments.find(item.first);
        const auto facts = facts_it == stats.instruments.end() ? InstrumentAggregationStats{} : facts_it->second;
        const auto age = facts.last_tick_received_us ? (now - facts.last_tick_received_us) / 1'000'000 : -1;
        receiving += age >= 0 && age < 30;
        const auto stored = store.InstrumentStats().find(item.first);
        ctp::Log("utc_us=", now, " event=instrument_status run_id=", store.RunId(),
            " instrument=", item.first, " subscription=", SubscriptionName(value.subscription),
            " error_id=", value.error_id, " callbacks_accepted=", facts.callbacks_accepted,
            " ticks_received=", facts.ticks_received, " last_tick_received_us=", facts.last_tick_received_us, " age_seconds=", age,
            " bars_written=", stored == store.InstrumentStats().end() ? 0 : stored->second.bars_written,
            " partial_bars=", stored == store.InstrumentStats().end() ? 0 : stored->second.partial_bars);
    }
    ctp::Log("utc_us=", now, " event=runtime_status run_id=", store.RunId(),
        " connected=", status.connected, " logged_in=", status.logged_in,
        " connections=", status.connections, " disconnections=", status.disconnections,
        " expected=", status.instruments.size(), " subscribed=", subscribed,
        " subscription_failed=", failed, " receiving_within_30s=", receiving,
        " ticks_received=", stats.ticks_received, " last_tick_received_us=", stats.last_tick_received_us,
        " callbacks_accepted=", stats.callbacks_accepted, " bars_written=", store.BarsWritten(),
        " partial_bars=", store.PartialBars(), " late_callbacks=", stats.late_callbacks,
        " invalid_trading_day=", stats.invalid_trading_day, " invalid_event_time=", stats.invalid_event_time,
        " unknown_instrument=", stats.unknown_instrument, " last_received_us=", stats.last_received_us,
        " last_commit_us=", store.LastCommitUs());
}

} // namespace

int RunCollector(const Config& config, const volatile std::sig_atomic_t& stop, ApiPtr api) {
    const std::string source = api ? "TEST DOUBLE - injected API" : std::string("CTP ") + CThostFtdcMdApi::GetApiVersion();
    DailyBarStore store(config.data_directory, config.instruments, source);
    AlignedBarAggregator aggregator(config.instruments);
    RuntimeStatusStore runtime_status(config.data_directory);
    RuntimeSnapshot initial;
    for (const auto& id : config.instruments) initial.session.instruments.emplace(id, InstrumentStatus{});
    runtime_status.Publish(initial, store, ProcessState::Starting);
    try {
        std::filesystem::create_directories(config.flow_path);
        std::string flow_path = config.flow_path.string();
        if (flow_path.back() != '/') flow_path += '/';
        if (!api) api.reset(CThostFtdcMdApi::CreateFtdcMdApi(flow_path.c_str(), false, false, true));
        if (!api) throw std::runtime_error("CreateFtdcMdApi returned null");
    } catch (...) {
        runtime_status.Publish(initial, store, ProcessState::Failed);
        throw;
    }
    CtpSession session(*api, config, aggregator, store.RunId());
    std::string front = config.front;
    const auto started_ms = SteadyMs();
    ctp::Log("utc_us=", NowUs(), " event=start run_id=", store.RunId(),
        " source=\"", source, "\" sqlite_version=", sqlite3_libversion(),
        " front=", front, " data_directory=", config.data_directory.string(),
        " bar_interval_us=", kBarIntervalUs, " close_grace_us=", kCloseGraceUs);
    const auto release = [&] {
        if (api) {
            api->RegisterSpi(nullptr);
            api.reset();
            session.Released();
        }
    };
    const auto flush = [&] {
        const auto bars = aggregator.CloseEligible(NowUs());
        if (bars.empty()) return;
        try {
            const auto inserted = store.Write(bars);
            ctp::Log("utc_us=", NowUs(), " event=bar_commit run_id=", store.RunId(),
                " rows=", inserted, " bars_written=", store.BarsWritten(),
                " partial_bars=", store.PartialBars(), " last_commit_us=", store.LastCommitUs());
        } catch (const std::exception& error) {
            ctp::Log("utc_us=", NowUs(), " event=persistence_failed run_id=", store.RunId(),
                " message=\"", error.what(), "\"");
            throw;
        }
    };
    const auto publish = [&](ProcessState state) {
        runtime_status.Publish(session.Snapshot(), store, state);
    };
    try {
        publish(ProcessState::Starting);
        api->RegisterSpi(&session);
        api->RegisterFront(front.data());
        api->Init();
        auto next_status_ms = started_ms;
        auto next_heartbeat_ms = started_ms;
        std::int64_t logged_in_ms = -1;
        while (!stop) {
            const auto now_ms = SteadyMs();
            session.Pump(now_ms);
            flush();
            if (logged_in_ms < 0 && session.HasLoggedIn()) logged_in_ms = now_ms;
            if (now_ms >= next_heartbeat_ms) {
                publish(logged_in_ms < 0 ? ProcessState::Starting : ProcessState::Running);
                next_heartbeat_ms = now_ms + 1000;
            }
            if (now_ms >= next_status_ms) {
                Report(session, store);
                next_status_ms = now_ms + config.status_interval_seconds * 1000;
            }
            if (config.run_seconds > 0 && logged_in_ms >= 0 &&
                now_ms - logged_in_ms >= static_cast<std::int64_t>(config.run_seconds) * 1000) break;
            std::this_thread::sleep_for(std::chrono::milliseconds(20));
        }
        release();
        session.CheckFailure();
        if (const auto deadline = aggregator.ShutdownGraceDeadline()) {
            while (NowUs() < *deadline) std::this_thread::sleep_for(std::chrono::milliseconds(10));
        }
        flush();
        Report(session, store);
        try { store.Finish(); }
        catch (const std::exception& error) {
            ctp::Log("utc_us=", NowUs(), " event=persistence_failed run_id=", store.RunId(),
                " message=\"", error.what(), "\"");
            throw;
        }
        publish(ProcessState::Stopped);
        ctp::Log("utc_us=", NowUs(), " event=stop run_id=", store.RunId(),
            " reason=", stop ? "signal" : "run_window_complete", " bars_written=", store.BarsWritten());
        return 0;
    } catch (...) {
        release();
        publish(ProcessState::Failed);
        ctp::Log("utc_us=", NowUs(), " event=collector_failed run_id=", store.RunId(),
            " bars_written=", store.BarsWritten());
        throw;
    }
}

} // namespace collector
