#pragma once

#include "client_support.hpp"

#include <chrono>
#include <cstdint>
#include <map>
#include <mutex>
#include <optional>
#include <set>
#include <string>
#include <vector>

namespace collector {

inline constexpr std::int64_t kBarIntervalUs = 15'000'000;
inline constexpr std::int64_t kCloseGraceUs = 1'000'000;

inline std::int64_t NowUs() {
    return std::chrono::duration_cast<std::chrono::microseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();
}

bool ValidTradingDay(const std::string& day);
bool ValidNumber(double value);
std::optional<std::int64_t> ParseEventTimeUs(const CThostFtdcDepthMarketDataField& data);

// All non-reserved v6.7.13 DepthMarketData fields. One list owns schema and binding order.
template<class Visitor> void VisitFacts(const CThostFtdcDepthMarketDataField& d, Visitor&& visit) {
#define FACT(name) visit(#name, d.name)
    FACT(TradingDay); FACT(ExchangeID); FACT(InstrumentID); FACT(ExchangeInstID);
    FACT(ActionDay); FACT(UpdateTime); FACT(UpdateMillisec);
    FACT(LastPrice); FACT(PreSettlementPrice); FACT(PreClosePrice); FACT(PreOpenInterest);
    FACT(OpenPrice); FACT(HighestPrice); FACT(LowestPrice); FACT(Volume); FACT(Turnover);
    FACT(OpenInterest); FACT(ClosePrice); FACT(SettlementPrice); FACT(UpperLimitPrice);
    FACT(LowerLimitPrice); FACT(PreDelta); FACT(CurrDelta);
    FACT(BidPrice1); FACT(BidVolume1); FACT(AskPrice1); FACT(AskVolume1);
    FACT(BidPrice2); FACT(BidVolume2); FACT(AskPrice2); FACT(AskVolume2);
    FACT(BidPrice3); FACT(BidVolume3); FACT(AskPrice3); FACT(AskVolume3);
    FACT(BidPrice4); FACT(BidVolume4); FACT(AskPrice4); FACT(AskVolume4);
    FACT(BidPrice5); FACT(BidVolume5); FACT(AskPrice5); FACT(AskVolume5);
    FACT(AveragePrice); FACT(BandingUpperPrice); FACT(BandingLowerPrice);
#undef FACT
}

struct MarketBar {
    CThostFtdcDepthMarketDataField close_facts{};
    std::int64_t bucket_start_us = 0;
    std::int64_t bucket_end_us = 0;
    std::optional<double> bar_open, bar_high, bar_low, bar_close;
    std::optional<std::int64_t> bar_volume;
    std::optional<double> bar_turnover;
    std::int64_t callback_count = 0;
    std::int64_t valid_last_price_count = 0;
    std::int64_t first_event_us = 0, last_event_us = 0;
    std::int64_t first_received_us = 0, last_received_us = 0, close_received_us = 0;
    bool is_partial = false;
    std::string partial_reasons = "[]";
};

struct InstrumentAggregationStats {
    std::uint64_t callbacks_accepted = 0;
    std::uint64_t late_callbacks = 0;
    std::uint64_t invalid_event_time = 0;
    std::int64_t last_received_us = 0;
};

struct AggregationStats {
    std::uint64_t callbacks_accepted = 0;
    std::uint64_t invalid_trading_day = 0;
    std::uint64_t invalid_event_time = 0;
    std::uint64_t unknown_instrument = 0;
    std::uint64_t late_callbacks = 0;
    std::uint64_t event_time_regressions = 0;
    std::int64_t last_received_us = 0;
    std::map<std::string, InstrumentAggregationStats> instruments;
};

class AlignedBarAggregator {
public:
    explicit AlignedBarAggregator(const std::vector<std::string>& instruments);

    bool Receive(const CThostFtdcDepthMarketDataField& data, std::int64_t received_us = NowUs());
    std::vector<MarketBar> CloseEligible(std::int64_t now_us = NowUs());
    std::optional<std::int64_t> ShutdownGraceDeadline(std::int64_t now_us = NowUs()) const;
    void MarkReconnect(std::int64_t now_us = NowUs());
    AggregationStats Stats() const;

private:
    struct Event {
        CThostFtdcDepthMarketDataField facts{};
        std::int64_t event_us = 0, received_us = 0, sequence = 0;
    };
    struct Bucket {
        std::vector<Event> events;
        std::set<std::string> reasons;
    };
    struct Stream {
        std::map<std::int64_t, Bucket> buckets;
        std::set<std::string> pending_reasons;
        std::optional<std::int64_t> volume_baseline;
        std::optional<double> turnover_baseline;
        std::int64_t latest_event_us = 0;
        std::int64_t sealed_through_us = 0;
        bool seen_event = false;
    };

    using Key = std::pair<std::string, std::string>;
    static bool IsContinuityBreak(const std::set<std::string>& reasons);
    static std::string ReasonsJson(const std::set<std::string>& reasons);
    MarketBar Finalize(Stream& stream, std::int64_t bucket_start_us, Bucket bucket);
    void MarkNextAffected(Stream& stream, std::int64_t after_bucket_us, const std::string& reason);

    const std::set<std::string> universe_;
    mutable std::mutex mutex_;
    std::map<Key, Stream> streams_;
    std::map<std::string, std::set<std::string>> pending_by_instrument_;
    std::int64_t sequence_ = 0;
    AggregationStats stats_;
};

} // namespace collector
