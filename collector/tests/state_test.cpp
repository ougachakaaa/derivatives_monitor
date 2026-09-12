#include "fixtures.hpp"
#include "test.hpp"
#include <atomic>
#include <thread>
#include <type_traits>
int main() {
    using namespace collector;
    CHECK(ValidTradingDay("20240229"));
    for (const auto* day : {"", "20260229", "20260931", "20261301", "../a/b/c", "20260001"}) CHECK(!ValidTradingDay(day));
    CHECK(!ValidNumber(std::numeric_limits<double>::max()));
    CHECK(!ValidNumber(std::numeric_limits<double>::quiet_NaN()));
    CHECK(!ValidNumber(std::numeric_limits<double>::infinity()));
    CHECK(ValidNumber(0)); CHECK(ValidNumber(-3));
    // Logical 15-second windows: received order wins, including older source time.
    {
        MarketSnapshotBuffer windows({"IF2609", "IO2609-C-4000"});
        auto first = Tick();
        CHECK(windows.Receive(first, 1000000));
        auto latest = first;
        ctp::CopyField(latest.UpdateTime, "09:30:59");
        latest.UpdateMillisec = 250;
        latest.LastPrice = 4020; latest.BidPrice1 = 4019; latest.AskPrice1 = 4021;
        latest.Volume = 100; latest.OpenInterest = 12000;
        CHECK(windows.Receive(latest, 14900000));
        const auto option = Tick("20260904", "IO2609-C-4000");
        CHECK(windows.Receive(option, 14950000));
        auto batch = windows.Materialize(15000000);
        CHECK(batch.size() == 2);
        const auto& row = batch[0];
        CHECK(row.sequence == 2 && row.received_us == 14900000 && row.snapshot_us == 15000000);
        // Compare every source field, not only LastPrice.
        std::vector<std::string> expected, actual;
        const auto stringify = [](const auto& value) {
            using T = std::decay_t<decltype(value)>;
            if constexpr (std::is_arithmetic_v<T>) return std::to_string(value);
            else return ctp::FieldString(value);
        };
        VisitFacts(latest, [&](const char*, const auto& value) { expected.push_back(stringify(value)); });
        VisitFacts(row.facts, [&](const char*, const auto& value) { actual.push_back(stringify(value)); });
        CHECK(actual == expected);
        CHECK(batch[1].received_us == 14950000 && batch[1].snapshot_us == 15000000);
        CHECK(windows.Materialize(30000000).empty());
        CHECK(windows.Materialize(45000000).empty());
        CHECK(windows.Receive(latest, 46000000)); // Identical callback is still a new fact.
        batch = windows.Materialize(60000000);
        CHECK(batch.size() == 1 && batch[0].sequence == 4);
        CHECK(batch[0].received_us == 46000000 && batch[0].snapshot_us == 60000000);
        CHECK(windows.Stats().accepted == 4);
    }
    MarketSnapshotBuffer state({"IF2609", "IO2609-C-4000"});
    auto tick = Tick();
    CHECK(state.Receive(tick, 10));
    tick.LastPrice = 4010;
    CHECK(state.Receive(tick, 11));
    tick.LastPrice = 9; // SDK buffer reuse cannot change copied state.
    auto rows = state.Materialize(20);
    CHECK(rows.size() == 1 && rows[0].facts.LastPrice == 4010);
    CHECK(rows[0].received_us == 11 && rows[0].snapshot_us == 20 && rows[0].sequence == 2);
    CHECK(state.Materialize(21).empty());
    CHECK(state.Receive(Tick("20260907"), 30));
    CHECK(state.Receive(Tick("20260904"), 31));
    Throws([&] { state.Receive(Tick("20260908"), 32); });
    rows = state.Materialize(40);
    CHECK(rows.size() == 2);
    CHECK(ctp::FieldString(rows[0].facts.TradingDay) == "20260904");
    CHECK(ctp::FieldString(rows[1].facts.TradingDay) == "20260907");
    CHECK(state.Receive(Tick("20260908"), 41));
    CHECK(!state.Receive(Tick("20260904"), 42));
    CHECK(!state.Receive(Tick("20260229"), 43));
    CHECK(!state.Receive(Tick("20260908", "unknown"), 44));
    CHECK(state.Stats().old_day == 1 && state.Stats().invalid_day == 1 && state.Stats().unknown_instrument == 1);
    std::atomic<bool> finished{false};
    std::thread producer([&] {
        for (int i = 0; i < 10000; ++i) {
            auto t = Tick("20260908"); t.Volume = i;
            state.Receive(t, 100 + i);
        }
        finished = true;
    });
    std::int64_t previous = 0;
    while (!finished) for (const auto& row : state.Materialize(20000)) {
        CHECK(row.sequence > previous); previous = row.sequence;
    }
    producer.join();
    rows = state.Materialize(20001);
    if (!rows.empty()) CHECK(rows.back().facts.Volume == 9999);
    CHECK(state.Stats().accepted == 10005);
    int fields = 0; VisitFacts(tick, [&](const char*, const auto&) { ++fields; });
    CHECK(fields == 46);
}
