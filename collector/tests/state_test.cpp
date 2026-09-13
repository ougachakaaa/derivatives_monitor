#include "domain/market.hpp"
#include "fixtures.hpp"
#include "test.hpp"

#include <atomic>
#include <thread>

int main() {
    using namespace collector;
    auto tick = Tick();
    CHECK(ValidTradingDay("20260228"));
    CHECK(!ValidTradingDay("20260229"));
    CHECK(ValidTradingDay("20240229"));
    CHECK(!ValidTradingDay("20261301"));
    CHECK(ParseEventTimeUs(tick).has_value());
    ctp::CopyField(tick.UpdateTime, "24:00:00");
    CHECK(!ParseEventTimeUs(tick));
    ctp::CopyField(tick.UpdateTime, "09:31:01");
    tick.UpdateMillisec = 1000;
    CHECK(!ParseEventTimeUs(tick));

    AlignedBarAggregator state({"IF2609"});
    auto valid = Tick();
    const auto event = *ParseEventTimeUs(valid);
    std::atomic<bool> start{false};
    std::vector<std::thread> producers;
    for (int worker = 0; worker < 4; ++worker) {
        producers.emplace_back([&, worker] {
            while (!start) {}
            for (int i = 0; i < 250; ++i) {
                auto value = valid;
                value.LastPrice = 4000 + worker;
                state.Receive(value, event + 100 + worker * 250 + i);
            }
        });
    }
    start = true;
    for (auto& producer : producers) producer.join();
    const auto rows = state.CloseEligible(event + kBarIntervalUs + kCloseGraceUs);
    CHECK(rows.size() == 1);
    CHECK(rows[0].callback_count == 1000);
    CHECK(state.Stats().callbacks_accepted == 1000);
    int fields = 0;
    VisitFacts(valid, [&](const char*, const auto&) { ++fields; });
    CHECK(fields == 46);
}
