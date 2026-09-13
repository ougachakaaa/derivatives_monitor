#include "domain/market.hpp"
#include "fixtures.hpp"
#include "test.hpp"

#include <cmath>

namespace {
CThostFtdcDepthMarketDataField At(const char* time, int millis, double price, int volume, double turnover,
                                  const char* day = "20260904", const char* action_day = "20260904") {
    auto tick = Tick(day);
    ctp::CopyField(tick.ActionDay, action_day);
    ctp::CopyField(tick.UpdateTime, time);
    tick.UpdateMillisec = millis;
    tick.LastPrice = price;
    tick.Volume = volume;
    tick.Turnover = turnover;
    return tick;
}
}

int main() {
    using namespace collector;
    {
        auto first = At("09:30:00", 500, 100, 20, 2000);
        auto second = At("09:30:14", 999, 103, 23, 2300);
        const auto start = *ParseEventTimeUs(first) - 500'000;
        AlignedBarAggregator bars({"IF2609"});
        CHECK(bars.Receive(first, start + 600'000));
        CHECK(bars.Receive(second, start + 15'500'000));
        CHECK(bars.CloseEligible(start + 15'999'999).empty());
        auto closed = bars.CloseEligible(start + 16'000'000);
        CHECK(closed.size() == 1);
        const auto& bar = closed[0];
        CHECK(bar.bucket_start_us == start && bar.bucket_end_us == start + kBarIntervalUs);
        CHECK(bar.callback_count == 2 && bar.valid_last_price_count == 2);
        CHECK(*bar.bar_open == 100 && *bar.bar_high == 103 && *bar.bar_low == 100 && *bar.bar_close == 103);
        CHECK(!bar.bar_volume && !bar.bar_turnover && bar.is_partial);
        CHECK(bar.partial_reasons == "[\"collector_start\",\"trading_day_init\",\"turnover_baseline_missing\",\"volume_baseline_missing\"]");
        CHECK(ctp::FieldString(bar.close_facts.UpdateTime) == "09:30:14");

        auto next1 = At("09:30:15", 0, 102, 23, 2300);
        auto next2 = At("09:30:29", 999, 105, 29, 2990);
        CHECK(bars.Receive(next1, start + 15'100'000));
        CHECK(bars.Receive(next2, start + 30'100'000));
        closed = bars.CloseEligible(start + 31'000'000);
        CHECK(closed.size() == 1 && !closed[0].is_partial);
        CHECK(*closed[0].bar_volume == 6 && std::abs(*closed[0].bar_turnover - 690) < 1e-9);
    }
    {
        AlignedBarAggregator bars({"IF2609"});
        auto later = At("09:31:10", 0, 110, 30, 3000);
        auto earlier = At("09:31:01", 0, 101, 21, 2100);
        auto equal = At("09:31:10", 0, 111, 31, 3100);
        const auto start = (*ParseEventTimeUs(earlier) / kBarIntervalUs) * kBarIntervalUs;
        CHECK(bars.Receive(later, start + 11'000'000));
        CHECK(bars.Receive(earlier, start + 12'000'000));
        CHECK(bars.Receive(equal, start + 12'100'000));
        auto closed = bars.CloseEligible(start + 16'000'000);
        CHECK(closed.size() == 1);
        CHECK(*closed[0].bar_open == 101 && *closed[0].bar_close == 111 && *closed[0].bar_high == 111);
        CHECK(closed[0].close_facts.Volume == 31);
        CHECK(closed[0].partial_reasons.find("event_time_regression") != std::string::npos);
        CHECK(closed[0].close_received_us == start + 12'100'000);
    }
    {
        AlignedBarAggregator bars({"IF2609"});
        auto base = At("10:00:01", 0, 100, 10, 1000);
        const auto start = (*ParseEventTimeUs(base) / kBarIntervalUs) * kBarIntervalUs;
        CHECK(bars.Receive(base, start + 2'000'000));
        CHECK(bars.CloseEligible(start + 16'000'000).size() == 1);
        auto empty = At("10:00:16", 0, std::numeric_limits<double>::max(), 10,
                        std::numeric_limits<double>::max());
        CHECK(bars.Receive(empty, start + 17'000'000));
        auto closed = bars.CloseEligible(start + 31'000'000);
        CHECK(closed.size() == 1 && closed[0].valid_last_price_count == 0);
        CHECK(!closed[0].bar_open && *closed[0].bar_volume == 0 && !closed[0].bar_turnover);
        CHECK(closed[0].partial_reasons == "[\"turnover_counter_invalid\"]");
        auto recovered = At("10:00:31", 0, 102, 14, 1400);
        CHECK(bars.Receive(recovered, start + 32'000'000));
        closed = bars.CloseEligible(start + 46'000'000);
        CHECK(closed[0].bar_volume && *closed[0].bar_volume == 4);
        CHECK(!closed[0].bar_turnover);
        CHECK(closed[0].partial_reasons == "[\"turnover_baseline_missing\"]");
    }
    {
        AlignedBarAggregator bars({"IF2609"});
        auto first = At("11:00:01", 0, 100, 10, 1000);
        const auto start = (*ParseEventTimeUs(first) / kBarIntervalUs) * kBarIntervalUs;
        CHECK(bars.Receive(first, start + 2'000'000));
        CHECK(bars.CloseEligible(start + 16'000'000).size() == 1);
        CHECK(!bars.Receive(first, start + 16'000'000));
        auto next = At("11:00:16", 0, 101, 11, 1100);
        CHECK(bars.Receive(next, start + 17'000'000));
        auto closed = bars.CloseEligible(start + 31'000'000);
        CHECK(closed.size() == 1 && closed[0].is_partial);
        CHECK(closed[0].partial_reasons.find("late_event") != std::string::npos);
        CHECK(!closed[0].bar_volume && !closed[0].bar_turnover);

        auto invalid = At("bad-time", 0, 1, 1, 1);
        CHECK(!bars.Receive(invalid, start + 32'000'000));
        auto after = At("11:00:31", 0, 102, 12, 1200);
        CHECK(bars.Receive(after, start + 32'100'000));
        closed = bars.CloseEligible(start + 46'000'000);
        CHECK(closed[0].partial_reasons.find("invalid_event_time") != std::string::npos);
    }
    {
        // A disconnect affects the open Bar, resets both baselines, then continuity recovers.
        AlignedBarAggregator bars({"IF2609"});
        auto base = At("13:00:01", 0, 100, 10, 1000);
        const auto start = (*ParseEventTimeUs(base) / kBarIntervalUs) * kBarIntervalUs;
        CHECK(bars.Receive(base, start + 2'000'000));
        CHECK(bars.CloseEligible(start + 16'000'000).size() == 1);
        auto interrupted = At("13:00:16", 0, 101, 12, 1200);
        CHECK(bars.Receive(interrupted, start + 17'000'000));
        bars.MarkReconnect(start + 18'000'000);
        auto closed = bars.CloseEligible(start + 31'000'000);
        CHECK(closed.size() == 1);
        CHECK(closed[0].partial_reasons == "[\"reconnect\",\"turnover_baseline_missing\",\"volume_baseline_missing\"]");
        auto recovered = At("13:00:31", 0, 102, 15, 1500);
        CHECK(bars.Receive(recovered, start + 32'000'000));
        closed = bars.CloseEligible(start + 46'000'000);
        CHECK(closed.size() == 1 && !closed[0].is_partial);
        CHECK(*closed[0].bar_volume == 3 && *closed[0].bar_turnover == 300);

        auto reset = At("13:00:46", 0, 103, 2, 1600);
        CHECK(bars.Receive(reset, start + 47'000'000));
        closed = bars.CloseEligible(start + 61'000'000);
        CHECK(!closed[0].bar_volume && *closed[0].bar_turnover == 100);
        CHECK(closed[0].partial_reasons == "[\"volume_counter_reset\"]");

        // A disconnect between buckets is carried to the next observed Bar.
        bars.MarkReconnect(start + 62'000'000);
        auto after_gap = At("13:01:16", 0, 104, 4, 1800);
        CHECK(bars.Receive(after_gap, start + 77'000'000));
        closed = bars.CloseEligible(start + 91'000'000);
        CHECK(closed[0].partial_reasons.find("reconnect") != std::string::npos);
        CHECK(!closed[0].bar_volume && !closed[0].bar_turnover);
    }
    {
        AlignedBarAggregator bars({"IF2609"});
        auto day1 = At("14:00:01", 0, 100, 10, 1000, "20260904", "20260904");
        auto day2 = At("14:00:01", 0, 101, 20, 2000, "20260907", "20260907");
        const auto first_us = *ParseEventTimeUs(day1);
        const auto second_us = *ParseEventTimeUs(day2);
        CHECK(bars.Receive(day1, first_us + 1));
        CHECK(bars.Receive(day2, second_us + 1));
        auto closed = bars.CloseEligible(second_us + kBarIntervalUs + kCloseGraceUs);
        CHECK(closed.size() == 2);
        CHECK(closed[0].partial_reasons.find("trading_day_init") != std::string::npos);
        CHECK(closed[1].partial_reasons.find("trading_day_init") != std::string::npos);
        CHECK(!closed[1].bar_volume && !closed[1].bar_turnover);
    }
    {
        AlignedBarAggregator bars({"IF2609"});
        std::int64_t previous = 0;
        for (const auto* time : {"23:59:00", "23:59:15", "23:59:30", "23:59:45"}) {
            auto tick = At(time, 0, 100, 1, 1, "20260905", "20260904");
            const auto event = *ParseEventTimeUs(tick);
            CHECK(bars.Receive(tick, event + 1));
            const auto start = (event / kBarIntervalUs) * kBarIntervalUs;
            if (previous) CHECK(start - previous == kBarIntervalUs);
            previous = start;
        }
        auto midnight = At("00:00:00", 0, 101, 2, 2, "20260905", "20260905");
        const auto midnight_us = *ParseEventTimeUs(midnight);
        CHECK(bars.Receive(midnight, midnight_us + 1));
        const auto closed = bars.CloseEligible(midnight_us + 1);
        CHECK(closed.size() == 3);
        CHECK(ctp::FieldString(closed.back().close_facts.TradingDay) == "20260905");
        CHECK(bars.CloseEligible(midnight_us + kCloseGraceUs).size() == 1);
        CHECK(bars.ShutdownGraceDeadline(midnight_us + kBarIntervalUs).value() == midnight_us + kBarIntervalUs + kCloseGraceUs);
    }
    {
        AlignedBarAggregator bars({"IF2609"});
        auto unknown = At("09:00:00", 0, 1, 1, 1); ctp::CopyField(unknown.InstrumentID, "UNKNOWN");
        auto bad_day = At("09:00:00", 0, 1, 1, 1, "20260229");
        CHECK(!bars.Receive(unknown, 1));
        CHECK(!bars.Receive(bad_day, 1));
        CHECK(bars.Stats().unknown_instrument == 1 && bars.Stats().invalid_trading_day == 1);
        CHECK(bars.CloseEligible(std::numeric_limits<std::int64_t>::max()).empty());
    }
}
