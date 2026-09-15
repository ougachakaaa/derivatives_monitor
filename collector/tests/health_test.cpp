#include "observability/runtime_status.hpp"
#include "sqlite_test.hpp"
#include "fixtures.hpp"

int main() {
    using namespace collector;
    TempDirectory temp;
    const auto path = temp.path / "collector-runtime.sqlite";
    std::string first_run;
    {
        DailyBarStore market(temp.path, {"IF2609"}, "TEST DOUBLE - runtime status");
        first_run = market.RunId();
        RuntimeStatusStore runtime(temp.path);
        CHECK(runtime.StartRun(market));
        const auto base = market.StartedUs();
        RuntimeSnapshot snapshot;
        snapshot.session.instruments.emplace("IF2609", InstrumentStatus{});
        CHECK(runtime.Publish(snapshot, market, ProcessState::Starting, base + 100));
        TestDb db(path);
        CHECK(db.Scalar("PRAGMA user_version") == "0");
        CHECK(db.Scalar("SELECT count(*) FROM sqlite_master WHERE type='table'") == "4");
        CHECK(db.Scalar("SELECT count(*) FROM runs") == "1");
        CHECK(db.Scalar("PRAGMA journal_mode") == "delete");
        CHECK(db.Scalar("SELECT trading_day FROM current_status") == "NULL");
        CHECK(db.Scalar("SELECT last_tick_received_us FROM current_status") == "NULL");
        CHECK(db.Scalar("SELECT last_market_commit_us FROM current_status") == "NULL");
        CHECK(db.Scalar("SELECT total_ticks_today FROM current_status") == "0");
        snapshot.session.connected = snapshot.session.logged_in = true;
        snapshot.session.instruments.at("IF2609").subscription = Subscription::Subscribed;
        AlignedBarAggregator aggregation({"IF2609"});
        auto tick = Tick("20260908");
        ctp::CopyField(tick.ActionDay, "20260907");
        ctp::CopyField(tick.UpdateTime, "23:59:59");
        auto event = *ParseEventTimeUs(tick);
        CHECK(aggregation.Receive(tick, event));
        ctp::CopyField(tick.ActionDay, "20260908");
        ctp::CopyField(tick.UpdateTime, "00:00:00");
        event = *ParseEventTimeUs(tick);
        CHECK(aggregation.Receive(tick, event));
        CHECK(aggregation.Stats().ticks_by_day.at("20260908") == 2);
        // Valid but late reception is evidence of feed activity, not Bar acceptance.
        CHECK(!aggregation.Receive(tick, event + kBarIntervalUs + kCloseGraceUs));
        CHECK(aggregation.Stats().ticks_by_day.at("20260908") == 3);
        ctp::CopyField(tick.TradingDay, "20260909");
        CHECK(aggregation.Receive(tick, event));
        ctp::CopyField(tick.TradingDay, "20260908");
        CHECK(aggregation.Receive(tick, event));
        auto invalid = tick;
        ctp::CopyField(invalid.UpdateTime, "invalid");
        CHECK(!aggregation.Receive(invalid, event));
        ctp::CopyField(invalid.TradingDay, "invalid");
        CHECK(!aggregation.Receive(invalid, event));
        invalid = tick; ctp::CopyField(invalid.InstrumentID, "unknown");
        CHECK(!aggregation.Receive(invalid, event));
        snapshot.aggregation = aggregation.Stats();
        CHECK(runtime.Publish(snapshot, market, ProcessState::Running, base + 200));
        CHECK(db.Scalar("SELECT trading_day FROM current_status") == "20260909");
        CHECK(db.Scalar("SELECT total_ticks_today FROM current_status") == "1");
        CHECK(db.Scalar("SELECT ticks_received FROM current_status") == "5");
        CHECK(db.Scalar("SELECT callbacks_accepted FROM current_status") == "4");
        CHECK(db.Scalar("SELECT late_callbacks FROM current_status") == "1");
        CHECK(db.Scalar("SELECT last_market_commit_us FROM current_status") == "NULL");
        const auto bars = aggregation.CloseEligible(event + kBarIntervalUs + kCloseGraceUs);
        CHECK(market.Write(bars) > 0);
        const auto committed = market.LastCommitUs();
        CHECK(committed > 0);
        bool failed = false;
        try { market.Write(bars); } catch (...) { failed = true; }
        CHECK(failed && market.LastCommitUs() == committed);
        CHECK(runtime.Publish(snapshot, market, ProcessState::Running, base + 300));
        CHECK(db.Scalar("SELECT last_market_commit_us FROM current_status") == std::to_string(committed));
        // A reader holding a snapshot prevents commit; both tables roll back together.
        db.Exec("BEGIN");
        CHECK(db.Scalar("SELECT heartbeat_us FROM current_status") == std::to_string(base + 300));
        CHECK(!runtime.Publish(snapshot, market, ProcessState::Running, base + 400));
        CHECK(db.Scalar("SELECT updated_us FROM instrument_status") == std::to_string(base + 300));
        db.Exec("ROLLBACK");
        CHECK(db.Scalar("SELECT heartbeat_us FROM current_status") == std::to_string(base + 300));
        CHECK(runtime.Publish(snapshot, market, ProcessState::Running, base + 500));
        CHECK(db.Scalar("SELECT updated_us FROM instrument_status") == std::to_string(base + 500));
        CHECK(runtime.Publish(snapshot, market, ProcessState::Stopped, base + 600));
        CHECK(db.Scalar("SELECT connected || logged_in || subscribed_count FROM current_status") == "000");
        CHECK(db.Scalar("SELECT subscription FROM instrument_status") == "not_sent");
        CHECK(db.Scalar("SELECT ticks_received FROM instrument_status") == "5");
        CHECK(db.Scalar("SELECT terminal_state FROM runs WHERE run_id='" + first_run + "'") == "stopped");
    }
    {
        DailyBarStore market(temp.path, {"IF2609"}, "TEST DOUBLE - new run");
        CHECK(market.RunId() != first_run);
        RuntimeStatusStore runtime(temp.path);
        CHECK(runtime.StartRun(market));
        RuntimeSnapshot snapshot;
        snapshot.session.instruments.emplace("IF2609", InstrumentStatus{});
        CHECK(runtime.Publish(snapshot, market, ProcessState::Starting));
        TestDb db(path, false);
        CHECK(db.Scalar("SELECT run_id FROM current_status") == market.RunId());
        CHECK(db.Scalar("SELECT ticks_received FROM current_status") == "0");
        CHECK(db.Scalar("SELECT trading_day FROM current_status") == "NULL");
        CHECK(db.Scalar("SELECT count(*) FROM runs") == "2");
        CHECK(db.Scalar("SELECT ended_us FROM runs WHERE run_id='" + market.RunId() + "'") == "NULL");
        db.Exec("ALTER TABLE runtime_snapshots ADD COLUMN incompatible INTEGER");
        CHECK(!runtime.Publish(snapshot, market, ProcessState::Starting));
    }
    {
        // TEST DOUBLE: complete natural windows use receive time directly and pending rows are immutable across retry.
        TempDirectory history;
        DailyBarStore market(history.path, {"IF2609"}, "TEST DOUBLE - runtime history");
        RuntimeStatusStore runtime(history.path);
        CHECK(runtime.StartRun(market));
        const auto first = ((market.StartedUs() + kBarIntervalUs - 1) / kBarIntervalUs) * kBarIntervalUs;
        {
            TestDb before(history.path / "collector-runtime.sqlite");
            CHECK(before.Scalar("SELECT count(*) FROM runtime_snapshots") == "0");
        }
        AlignedBarAggregator aggregation({"IF2609"});
        auto tick = Tick();
        aggregation.Receive(tick, first + 1); // late is still a legal receive-time fact
        RuntimeSnapshot snapshot;
        snapshot.session.instruments.emplace("IF2609", InstrumentStatus{});
        snapshot.aggregation = aggregation.Stats();
        CHECK(runtime.Publish(snapshot, market, ProcessState::Starting, first + kBarIntervalUs + 7));
        TestDb db(history.path / "collector-runtime.sqlite", false);
        CHECK(db.Scalar("SELECT count(*) FROM runtime_snapshots") == "1");
        CHECK(db.Scalar("SELECT interval_start_us FROM runtime_snapshots") == std::to_string(first));
        CHECK(db.Scalar("SELECT tick_count FROM runtime_snapshots") == "1");
        CHECK(db.Scalar("SELECT last_tick_received_us FROM runtime_snapshots") == std::to_string(first + 1));
        db.Rejects("INSERT INTO runtime_snapshots VALUES('" + market.RunId() + "',1,2,3,'running',0,0,1,0,0,0,0,0,NULL,NULL)");
        db.Rejects("INSERT INTO runs VALUES('invalid',1,NULL,NULL,'[]','TEST DOUBLE')");

        aggregation.Receive(tick, first + kBarIntervalUs + 2);
        snapshot.aggregation = aggregation.Stats();
        db.Exec("BEGIN");
        CHECK(db.Scalar("SELECT count(*) FROM runtime_snapshots") == "1");
        const auto observed = first + 2 * kBarIntervalUs + 9;
        CHECK(!runtime.Publish(snapshot, market, ProcessState::Running, observed));
        CHECK(db.Scalar("SELECT count(*) FROM runtime_snapshots") == "1");
        db.Exec("ROLLBACK");
        CHECK(runtime.Publish(snapshot, market, ProcessState::Running, observed + 100));
        CHECK(db.Scalar("SELECT count(*) FROM runtime_snapshots") == "2");
        CHECK(db.Scalar("SELECT observed_us FROM runtime_snapshots ORDER BY interval_start_us DESC LIMIT 1") ==
              std::to_string(observed));
        CHECK(db.Scalar("SELECT tick_count FROM runtime_snapshots ORDER BY interval_start_us DESC LIMIT 1") == "1");

        // A forward jump leaves unknown gaps; a backward jump may resume only with a newly observed full window.
        CHECK(runtime.Publish(snapshot, market, ProcessState::Running, first + 4 * kBarIntervalUs));
        CHECK(db.Scalar("SELECT count(*) FROM runtime_snapshots") == "2");
        CHECK(runtime.Publish(snapshot, market, ProcessState::Running, first + 5 * kBarIntervalUs + 1));
        CHECK(db.Scalar("SELECT count(*) FROM runtime_snapshots") == "3");
        CHECK(db.Scalar("SELECT max(interval_start_us) FROM runtime_snapshots") ==
              std::to_string(first + 4 * kBarIntervalUs));
        CHECK(runtime.Publish(snapshot, market, ProcessState::Running, first + kBarIntervalUs + 10));
        CHECK(runtime.Publish(snapshot, market, ProcessState::Running, first + 3 * kBarIntervalUs + 1));
        CHECK(db.Scalar("SELECT count(*) FROM runtime_snapshots") == "4");
        CHECK(db.Scalar("SELECT count(*) FROM runtime_snapshots WHERE interval_start_us=" +
                        std::to_string(first + 3 * kBarIntervalUs)) == "0");
        CHECK(runtime.Publish(snapshot, market, ProcessState::Stopped, first + 6 * kBarIntervalUs));
        CHECK(db.Scalar("SELECT count(*) FROM runtime_snapshots") == "4");
        CHECK(db.Scalar("SELECT ended_us FROM runs WHERE run_id='" + market.RunId() + "'") ==
              std::to_string(first + 6 * kBarIntervalUs));
        CHECK(db.Scalar("SELECT terminal_state FROM runs WHERE run_id='" + market.RunId() + "'") == "stopped");
    }
    {
        // TEST DOUBLE: the retired two-table runtime database is incompatible and is not modified.
        TempDirectory old;
        const auto old_path = old.path / "collector-runtime.sqlite";
        {
            std::ofstream(old_path).close();
            TestDb db(old_path, false);
            db.Exec("PRAGMA user_version=1;CREATE TABLE current_status(singleton INTEGER);"
                    "CREATE TABLE instrument_status(instrument_id TEXT)");
        }
        DailyBarStore market(old.path, {"IF2609"}, "TEST DOUBLE - old schema");
        RuntimeStatusStore runtime(old.path);
        CHECK(!runtime.StartRun(market));
        TestDb db(old_path);
        CHECK(db.Scalar("SELECT count(*) FROM sqlite_master WHERE type='table'") == "2");
        CHECK(db.Scalar("SELECT count(*) FROM sqlite_master WHERE name='runs'") == "0");
    }
    {
        TempDirectory corrupt;
        std::ofstream(corrupt.path / "collector-runtime.sqlite") << "TEST DOUBLE - corrupt database";
        DailyBarStore market(corrupt.path, {"IF2609"}, "TEST DOUBLE");
        RuntimeStatusStore runtime(corrupt.path);
        CHECK(!runtime.StartRun(market));
        CHECK(std::filesystem::file_size(corrupt.path / "collector-runtime.sqlite") == std::string("TEST DOUBLE - corrupt database").size());
    }
    CHECK(!std::filesystem::exists(temp.path / ".collector-status.json"));
    CHECK(!std::filesystem::exists(temp.path / ".collector-coverage.json"));
}
