#pragma once
#include "client_support.hpp"
#include <chrono>
#include <cmath>
#include <cstdint>
#include <limits>
#include <set>

namespace collector {
inline std::int64_t NowUs() {
    return std::chrono::duration_cast<std::chrono::microseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();
}

inline bool ValidTradingDay(const std::string& day) {
    if (day.size() != 8 || day.find_first_not_of("0123456789") != std::string::npos) return false;
    const int y = std::stoi(day.substr(0, 4)), m = std::stoi(day.substr(4, 2)), d = std::stoi(day.substr(6, 2));
    if (y < 1900 || y > 9999 || m < 1 || m > 12) return false;
    const int lengths[] = {31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};
    const bool leap = y % 4 == 0 && (y % 100 != 0 || y % 400 == 0);
    return d >= 1 && d <= lengths[m - 1] + (m == 2 && leap ? 1 : 0);
}

// The CTP missing-double sentinel is DBL_MAX; also normalize non-finite input.
inline bool ValidNumber(double value) {
    return std::isfinite(value) && std::abs(value) != std::numeric_limits<double>::max();
}

// All non-reserved v6.7.13 DepthMarketData fields. One list defines schema and binding.
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

struct Snapshot {
    CThostFtdcDepthMarketDataField facts{};
    std::int64_t received_us = 0;
    std::int64_t snapshot_us = 0;
    std::int64_t sequence = 0;
};
struct SnapshotBufferStats {
    std::uint64_t accepted = 0, invalid_day = 0, unknown_instrument = 0, old_day = 0;
    std::int64_t last_received_us = 0;
};

class MarketSnapshotBuffer {
public:
    explicit MarketSnapshotBuffer(const std::vector<std::string>& instruments)
        : universe_(instruments.begin(), instruments.end()) {}

    bool Receive(const CThostFtdcDepthMarketDataField& data, std::int64_t received_us) {
        const auto day = ctp::FieldString(data.TradingDay);
        const auto id = ctp::FieldString(data.InstrumentID);
        std::lock_guard<std::mutex> lock(mutex_);
        if (!ValidTradingDay(day)) { ++stats_.invalid_day; return false; }
        if (!universe_.count(id)) { ++stats_.unknown_instrument; return false; }
        if (!days_.count(day) && days_.size() == 2) {
            const auto oldest = days_.begin();
            if (day < oldest->first) { ++stats_.old_day; return false; }
            for (const auto& entry : oldest->second)
                if (entry.second.dirty) throw std::runtime_error("third trading day would evict unmaterialized state");
            days_.erase(oldest);
        }
        auto& entry = days_[day][id];
        entry.value = {data, received_us, 0, ++sequence_};
        entry.dirty = true;
        ++stats_.accepted;
        stats_.last_received_us = received_us;
        return true;
    }

    std::vector<Snapshot> Materialize(std::int64_t snapshot_us) {
        std::vector<Snapshot> result;
        std::lock_guard<std::mutex> lock(mutex_);
        for (auto& day : days_) for (auto& item : day.second) {
            auto& entry = item.second;
            if (!entry.dirty) continue;
            auto snapshot = entry.value;
            snapshot.snapshot_us = snapshot_us;
            result.push_back(snapshot);
            entry.dirty = false;
        }
        return result;
    }

    SnapshotBufferStats Stats() const { std::lock_guard<std::mutex> lock(mutex_); return stats_; }
private:
    struct Entry { Snapshot value; bool dirty = false; };
    const std::set<std::string> universe_;
    std::map<std::string, std::map<std::string, Entry>> days_;
    mutable std::mutex mutex_;
    std::int64_t sequence_ = 0;
    SnapshotBufferStats stats_;
};
} // namespace collector
