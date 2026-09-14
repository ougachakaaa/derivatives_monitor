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
        RuntimeSnapshot snapshot;
        snapshot.session.instruments.emplace("IF2609", InstrumentStatus{});
        CHECK(runtime.Publish(snapshot, market, ProcessState::Starting, 100));
        TestDb db(path);
        CHECK(db.Scalar("PRAGMA user_version") == "1");
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
        CHECK(runtime.Publish(snapshot, market, ProcessState::Running, 200));
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
        CHECK(runtime.Publish(snapshot, market, ProcessState::Running, 300));
        CHECK(db.Scalar("SELECT last_market_commit_us FROM current_status") == std::to_string(committed));
        // A reader holding a snapshot prevents commit; both tables roll back together.
        db.Exec("BEGIN");
        CHECK(db.Scalar("SELECT heartbeat_us FROM current_status") == "300");
        CHECK(!runtime.Publish(snapshot, market, ProcessState::Running, 400));
        CHECK(db.Scalar("SELECT updated_us FROM instrument_status") == "300");
        db.Exec("ROLLBACK");
        CHECK(db.Scalar("SELECT heartbeat_us FROM current_status") == "300");
        CHECK(runtime.Publish(snapshot, market, ProcessState::Running, 500));
        CHECK(db.Scalar("SELECT updated_us FROM instrument_status") == "500");
        CHECK(runtime.Publish(snapshot, market, ProcessState::Stopped, 600));
        CHECK(db.Scalar("SELECT connected || logged_in || subscribed_count FROM current_status") == "000");
        CHECK(db.Scalar("SELECT subscription FROM instrument_status") == "not_sent");
        CHECK(db.Scalar("SELECT ticks_received FROM instrument_status") == "5");
        CHECK(runtime.Publish(snapshot, market, ProcessState::Failed, 700));
        CHECK(db.Scalar("SELECT process_state FROM current_status") == "failed");
    }
    {
        DailyBarStore market(temp.path, {"IF2609"}, "TEST DOUBLE - new run");
        CHECK(market.RunId() != first_run);
        RuntimeStatusStore runtime(temp.path);
        RuntimeSnapshot snapshot;
        snapshot.session.instruments.emplace("IF2609", InstrumentStatus{});
        CHECK(runtime.Publish(snapshot, market, ProcessState::Starting));
        TestDb db(path, false);
        CHECK(db.Scalar("SELECT run_id FROM current_status") == market.RunId());
        CHECK(db.Scalar("SELECT ticks_received FROM current_status") == "0");
        CHECK(db.Scalar("SELECT trading_day FROM current_status") == "NULL");
        db.Exec("PRAGMA user_version=99");
        CHECK(!runtime.Publish(snapshot, market, ProcessState::Starting));
        CHECK(db.Scalar("PRAGMA user_version") == "99");
    }
    {
        TempDirectory corrupt;
        std::ofstream(corrupt.path / "collector-runtime.sqlite") << "TEST DOUBLE - corrupt database";
        DailyBarStore market(corrupt.path, {"IF2609"}, "TEST DOUBLE");
        RuntimeStatusStore runtime(corrupt.path);
        CHECK(!runtime.Publish({}, market, ProcessState::Starting));
        CHECK(std::filesystem::file_size(corrupt.path / "collector-runtime.sqlite") == std::string("TEST DOUBLE - corrupt database").size());
    }
    CHECK(!std::filesystem::exists(temp.path / ".collector-status.json"));
    CHECK(!std::filesystem::exists(temp.path / ".collector-coverage.json"));
}
