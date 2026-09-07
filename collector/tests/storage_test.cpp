#include "storage.hpp"
#include "fixtures.hpp"
#include "sqlite_test.hpp"
#include <type_traits>
int main() {
    using namespace collector;
    TempDirectory temp;
    const auto path = temp.path / "20260904.sqlite";
    Snapshot a{Tick(), 10, 20, 1}, b{Tick("20260907", "IO2609-C-4000"), 30, 40, 2};
    // Fill every numeric field to catch omissions/binding order errors.
    a.facts.LastPrice = -10.5; a.facts.BidPrice1 = 4000; a.facts.AskVolume5 = 12;
    std::string first_run;
    {
        DailyStore store(temp.path, 1000, {"IF2609", "IO2609-C-4000"}, "TEST DOUBLE - storage fixture");
        first_run = store.RunId();
        Throws([&] { DailyStore second(temp.path, 1000, {"IF2609"}, "TEST DOUBLE - storage fixture"); });
        CHECK(store.Write({a, b}) == 2);
        CHECK(store.Write({a, b}) == 0);
        CHECK(store.Written() == 2 && store.LastCommitUs() > 0);
        TestDb reader(path);
        CHECK(sqlite3_db_readonly(reader.db, "main") == 1);
        CHECK(reader.Scalar("PRAGMA journal_mode") == "wal");
        CHECK(reader.Scalar("SELECT trading_day FROM dataset") == "20260904");
        CHECK(reader.Scalar("SELECT count(*) FROM snapshots") == "1");
        CHECK(reader.Scalar("SELECT AskPrice5 IS NULL FROM snapshots") == "1");
        VisitFacts(a.facts, [&](const char* name, const auto& value) {
            using T = std::decay_t<decltype(value)>;
            const auto actual = reader.Scalar(std::string("SELECT ") + name + " FROM snapshots LIMIT 1");
            if constexpr (std::is_floating_point_v<T>) {
                if (!ValidNumber(value)) CHECK(actual == "NULL");
                else CHECK(std::abs(std::stod(actual) - value) < 1e-9);
            } else if constexpr (std::is_integral_v<T>) CHECK(std::stoll(actual) == value);
            else CHECK(actual == ctp::FieldString(value));
        });
        CHECK(sqlite3_exec(reader.db, "DELETE FROM snapshots", nullptr, nullptr, nullptr) == SQLITE_READONLY);
        reader.Exec("BEGIN"); CHECK(reader.Scalar("SELECT count(*) FROM snapshots") == "1");
        auto c = a; c.sequence = 3; c.facts.Volume = 77;
        CHECK(store.Write({c}) == 1); // Existing reader transaction cannot block the writer.
        CHECK(reader.Scalar("SELECT count(*) FROM snapshots") == "1");
        reader.Exec("COMMIT"); CHECK(reader.Scalar("SELECT count(*) FROM snapshots") == "2");
        TestDb injection(path, false);
        injection.Exec("CREATE TRIGGER fail_batch BEFORE INSERT ON snapshots WHEN NEW.sequence=5 BEGIN SELECT RAISE(ABORT,'injected failure'); END");
        auto d = a, e = a; d.sequence = 4; e.sequence = 5;
        Throws([&] { store.Write({d, e}); });
        CHECK(reader.Scalar("SELECT count(*) FROM snapshots") == "2");
        CHECK(store.Written() == 3);
        injection.Exec("DROP TRIGGER fail_batch");
        injection.Exec("BEGIN IMMEDIATE");
        Throws([&] { store.Write({d}); });
        injection.Exec("ROLLBACK");
        CHECK(store.Write({d}) == 1);
        auto invalid = a; ctp::CopyField(invalid.facts.TradingDay, "20260229");
        Throws([&] { store.Write({invalid}); });
        CHECK(sqlite3_exec(injection.db, "UPDATE snapshots SET TradingDay='20260907'", nullptr, nullptr, nullptr) == SQLITE_CONSTRAINT);
        store.Finish();
        CHECK(reader.Scalar("SELECT stopped_us IS NOT NULL FROM runs") == "1");
    }
    {
        DailyStore restart(temp.path, 15000, {"IF2609"}, "TEST DOUBLE - storage fixture");
        CHECK(restart.RunId() != first_run);
        CHECK(restart.Write({a}) == 1);
        restart.Finish();
    }
    {
        TestDb reader(path);
        CHECK(reader.Scalar("PRAGMA integrity_check") == "ok");
        CHECK(reader.Scalar("SELECT count(*) FROM runs") == "2");
        CHECK(reader.Scalar("SELECT count(*) FROM runs WHERE snapshot_interval_ms=1000") == "1");
        CHECK(reader.Scalar("SELECT count(*) FROM runs WHERE snapshot_interval_ms=15000") == "1");
        CHECK(reader.Scalar("PRAGMA user_version") == "1");
        CHECK(reader.Scalar("SELECT schema_version FROM dataset") == "1");
        CHECK(reader.Scalar("SELECT count(*) FROM snapshots WHERE received_us=10 AND snapshot_us=20") == "4");
        CHECK(reader.Scalar("SELECT count(*) FROM snapshots WHERE ActionDay='20260903' AND UpdateTime='09:31:01' AND UpdateMillisec=500") == "4");
        CHECK(reader.Scalar("SELECT count(*) FROM snapshots") == "4");
        TestDb day2(temp.path / "20260907.sqlite");
        CHECK(day2.Scalar("SELECT count(*) FROM snapshots WHERE TradingDay='20260907'") == "1");
    }
    {
        TestDb injection(path, false); injection.Exec("PRAGMA user_version=99");
        DailyStore store(temp.path, 1000, {"IF2609"}, "TEST DOUBLE - storage fixture");
        Throws([&] { store.Write({a}); });
        injection.Exec("PRAGMA user_version=1; UPDATE dataset SET trading_day='20260908'");
        Throws([&] { store.Write({a}); });
        CHECK(injection.Scalar("SELECT count(*) FROM snapshots") == "4");
    }
}
