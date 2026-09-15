#include "persistence/sqlite_store.hpp"
#include "fixtures.hpp"
#include "sqlite_test.hpp"

#include <type_traits>

namespace {
collector::MarketBar Bar(const char* day, const char* id, const char* time, int price, int volume, double turnover,
                         bool partial = false) {
    collector::MarketBar bar;
    bar.close_facts = Tick(day, id);
    ctp::CopyField(bar.close_facts.ActionDay, day);
    ctp::CopyField(bar.close_facts.UpdateTime, time);
    bar.close_facts.UpdateMillisec = 0;
    bar.close_facts.LastPrice = price;
    bar.close_facts.Volume = volume;
    bar.close_facts.Turnover = turnover;
    const auto event = *collector::ParseEventTimeUs(bar.close_facts);
    bar.bucket_start_us = event / collector::kBarIntervalUs * collector::kBarIntervalUs;
    bar.bucket_end_us = bar.bucket_start_us + collector::kBarIntervalUs;
    bar.bar_open = bar.bar_high = bar.bar_low = bar.bar_close = price;
    bar.bar_volume = volume;
    bar.bar_turnover = turnover;
    bar.callback_count = bar.valid_last_price_count = 1;
    bar.first_event_us = bar.last_event_us = event;
    bar.first_received_us = bar.last_received_us = bar.close_received_us = event + 1000;
    bar.is_partial = partial;
    bar.partial_reasons = partial ? "[\"collector_start\"]" : "[]";
    return bar;
}
}

int main() {
    using namespace collector;
    TempDirectory temp;
    const auto path = temp.path / "20260904.sqlite";
    auto first = Bar("20260904", "IF2609", "09:30:01", 4001, 10, 1000, true);
    first.close_facts.AskPrice5 = std::numeric_limits<double>::max();
    auto second_day = Bar("20260907", "IO2609-C-4000", "09:30:01", 100, 2, 20);
    std::string first_run;
    {
        DailyBarStore store(temp.path, {"IF2609", "IO2609-C-4000"}, "TEST DOUBLE - storage fixture");
        first_run = store.RunId();
        Throws([&] { DailyBarStore duplicate(temp.path, {"IF2609"}, "TEST DOUBLE - lock"); });
        CHECK(store.Write({second_day, first}) == 2);
        CHECK(store.BarsWritten() == 2 && store.PartialBars() == 1 && store.LastCommitUs() > 0);
        const auto commit_interval = (store.LastCommitUs() / kBarIntervalUs) * kBarIntervalUs;
        CHECK(store.RuntimeCommits().at(commit_interval).bars == 2);
        CHECK(store.RuntimeCommits().at(commit_interval).partial_bars == 1);
        CHECK(store.RuntimeCommits().at(commit_interval).last_commit_us == store.LastCommitUs());

        TestDb reader(path);
        CHECK(sqlite3_db_readonly(reader.db, "main") == 1);
        CHECK(reader.Scalar("PRAGMA journal_mode") == "wal");
        CHECK(reader.Scalar("PRAGMA user_version") == "2");
        CHECK(reader.Scalar("SELECT trading_day||':'||schema_version||':'||bar_interval_us||':'||close_grace_us FROM dataset") ==
              "20260904:2:15000000:1000000");
        CHECK(reader.Scalar("SELECT count(*) FROM market_bars") == "1");
        CHECK(reader.Scalar("SELECT AskPrice5 IS NULL FROM market_bars") == "1");
        CHECK(reader.Scalar("SELECT bar_open||':'||bar_close||':'||is_partial FROM market_bars") == "4001.0:4001.0:1");
        CHECK(reader.Scalar("SELECT source LIKE '%TEST DOUBLE%' FROM runs") == "1");
        VisitFacts(first.close_facts, [&](const char* name, const auto& value) {
            const auto actual = reader.Scalar(std::string("SELECT ") + name + " FROM market_bars LIMIT 1");
            using T = std::decay_t<decltype(value)>;
            if constexpr (std::is_floating_point_v<T>) {
                if (!ValidNumber(value)) CHECK(actual == "NULL");
                else CHECK(std::abs(std::stod(actual) - value) < 1e-9);
            } else if constexpr (std::is_integral_v<T>) CHECK(std::stoll(actual) == value);
            else CHECK(actual == ctp::FieldString(value));
        });
        CHECK(sqlite3_exec(reader.db, "DELETE FROM market_bars", nullptr, nullptr, nullptr) == SQLITE_READONLY);

        // Canonical identity is append-only: duplicate insertion is an invariant failure, not an upsert.
        Throws([&] { store.Write({first}); });
        CHECK(reader.Scalar("SELECT count(*) FROM market_bars") == "1");
        CHECK(store.BarsWritten() == 2);

        auto next = Bar("20260904", "IF2609", "09:30:16", 4002, 12, 1200);
        reader.Exec("BEGIN");
        CHECK(reader.Scalar("SELECT count(*) FROM market_bars") == "1");
        CHECK(store.Write({next}) == 1);
        CHECK(reader.Scalar("SELECT count(*) FROM market_bars") == "1");
        reader.Exec("COMMIT");
        CHECK(reader.Scalar("SELECT count(*) FROM market_bars") == "2");

        TestDb injection(path, false);
        auto third = Bar("20260904", "IF2609", "09:30:31", 4003, 13, 1300);
        auto fourth = Bar("20260904", "IF2609", "09:30:46", 4004, 14, 1400);
        injection.Exec("CREATE TRIGGER fail_batch BEFORE INSERT ON market_bars WHEN NEW.bar_close=4004 BEGIN SELECT RAISE(ABORT,'TEST DOUBLE failure'); END");
        Throws([&] { store.Write({fourth, third}); });
        CHECK(reader.Scalar("SELECT count(*) FROM market_bars") == "2");
        injection.Exec("DROP TRIGGER fail_batch");
        CHECK(store.Write({fourth, third}) == 2);
        CHECK(reader.Scalar("SELECT group_concat(bar_close,',') FROM market_bars ORDER BY id") == "4001.0,4002.0,4003.0,4004.0");
        CHECK(sqlite3_exec(injection.db, "UPDATE market_bars SET TradingDay='20260907'", nullptr, nullptr, nullptr) == SQLITE_CONSTRAINT);
        store.Finish();
        CHECK(reader.Scalar("SELECT stopped_us IS NOT NULL FROM runs") == "1");
    }
    {
        DailyBarStore restart(temp.path, {"IF2609"}, "TEST DOUBLE - restart");
        CHECK(restart.RunId() != first_run);
        auto appended = Bar("20260904", "IF2609", "09:31:01", 4005, 15, 1500);
        CHECK(restart.Write({appended}) == 1);
        Throws([&] { restart.Write({first}); });
        restart.Finish();
    }
    {
        TestDb reader(path);
        CHECK(reader.Scalar("PRAGMA integrity_check") == "ok");
        CHECK(reader.Scalar("SELECT count(*) FROM runs") == "2");
        CHECK(reader.Scalar("SELECT count(*) FROM market_bars") == "5");
        CHECK(reader.Scalar("SELECT count(*) FROM runs WHERE stopped_us IS NULL") == "0");
        TestDb day2(temp.path / "20260907.sqlite");
        CHECK(day2.Scalar("SELECT count(*) FROM market_bars WHERE TradingDay='20260907'") == "1");
    }
    {
        const auto old_path = temp.path / "20260908.sqlite";
        sqlite3* db = nullptr;
        CHECK(sqlite3_open(old_path.c_str(), &db) == SQLITE_OK);
        CHECK(sqlite3_exec(db, "PRAGMA user_version=1;CREATE TABLE snapshots(id INTEGER);", nullptr, nullptr, nullptr) == SQLITE_OK);
        sqlite3_close(db);
        DailyBarStore store(temp.path, {"IF2609"}, "TEST DOUBLE - v1 rejection");
        auto old = Bar("20260908", "IF2609", "09:30:01", 1, 1, 1);
        Throws([&] { store.Write({old}); });
        TestDb unchanged(old_path);
        CHECK(unchanged.Scalar("PRAGMA user_version") == "1");
        CHECK(unchanged.Scalar("SELECT count(*) FROM snapshots") == "0");
    }
    {
        // Version labels cannot disguise a database whose physical v2 contract is incomplete.
        const auto fake_path = temp.path / "20260909.sqlite";
        sqlite3* db = nullptr;
        CHECK(sqlite3_open(fake_path.c_str(), &db) == SQLITE_OK);
        CHECK(sqlite3_exec(db,
            "PRAGMA application_id=1145914161;PRAGMA user_version=2;"
            "CREATE TABLE dataset(singleton INTEGER PRIMARY KEY,trading_day TEXT,schema_version INTEGER,bar_interval_us INTEGER,close_grace_us INTEGER);"
            "INSERT INTO dataset VALUES(1,'20260909',2,15000000,1000000);"
            "CREATE TABLE runs(run_id TEXT PRIMARY KEY,started_us INTEGER,stopped_us INTEGER,last_commit_us INTEGER,instruments TEXT,source TEXT);"
            "CREATE TABLE market_bars(id INTEGER PRIMARY KEY,run_id TEXT,TradingDay TEXT,InstrumentID TEXT,bucket_start_us INTEGER);",
            nullptr, nullptr, nullptr) == SQLITE_OK);
        sqlite3_close(db);
        DailyBarStore store(temp.path, {"IF2609"}, "TEST DOUBLE - fake v2 rejection");
        auto fake = Bar("20260909", "IF2609", "09:30:01", 1, 1, 1);
        Throws([&] { store.Write({fake}); });
        TestDb unchanged(fake_path);
        CHECK(unchanged.Scalar("SELECT count(*) FROM market_bars") == "0");
    }
}
