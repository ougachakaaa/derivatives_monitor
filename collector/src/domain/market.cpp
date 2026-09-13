#include "domain/market.hpp"

#include <algorithm>
#include <cmath>
#include <iomanip>
#include <limits>
#include <sstream>
#include <tuple>

namespace collector {
namespace {

bool Leap(int year) { return year % 4 == 0 && (year % 100 != 0 || year % 400 == 0); }

bool ParseDay(const std::string& text, int& year, int& month, int& day) {
    if (text.size() != 8 || text.find_first_not_of("0123456789") != std::string::npos) return false;
    year = std::stoi(text.substr(0, 4));
    month = std::stoi(text.substr(4, 2));
    day = std::stoi(text.substr(6, 2));
    if (year < 1900 || year > 9999 || month < 1 || month > 12) return false;
    const int lengths[] = {31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};
    return day >= 1 && day <= lengths[month - 1] + (month == 2 && Leap(year) ? 1 : 0);
}

// Howard Hinnant's civil calendar mapping, yielding days since 1970-01-01.
std::int64_t DaysFromCivil(int year, unsigned month, unsigned day) {
    year -= month <= 2;
    const int era = (year >= 0 ? year : year - 399) / 400;
    const unsigned yoe = static_cast<unsigned>(year - era * 400);
    const unsigned doy = (153 * (month + (month > 2 ? -3 : 9)) + 2) / 5 + day - 1;
    const unsigned doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    return static_cast<std::int64_t>(era) * 146097 + static_cast<int>(doe) - 719468;
}

bool ParseClock(const std::string& text, int& hour, int& minute, int& second) {
    if (text.size() != 8 || text[2] != ':' || text[5] != ':') return false;
    for (const int i : {0, 1, 3, 4, 6, 7}) if (text[i] < '0' || text[i] > '9') return false;
    hour = (text[0] - '0') * 10 + text[1] - '0';
    minute = (text[3] - '0') * 10 + text[4] - '0';
    second = (text[6] - '0') * 10 + text[7] - '0';
    return hour < 24 && minute < 60 && second < 60;
}

std::int64_t FloorBucket(std::int64_t event_us) {
    const auto quotient = event_us / kBarIntervalUs;
    const auto remainder = event_us % kBarIntervalUs;
    return (remainder < 0 ? quotient - 1 : quotient) * kBarIntervalUs;
}

bool ValidVolume(int volume) { return volume >= 0; }
bool ValidTurnover(double turnover) { return ValidNumber(turnover) && turnover >= 0; }

} // namespace

bool ValidTradingDay(const std::string& day) {
    int year = 0, month = 0, date = 0;
    return ParseDay(day, year, month, date);
}

bool ValidNumber(double value) {
    return std::isfinite(value) && std::abs(value) != std::numeric_limits<double>::max();
}

std::optional<std::int64_t> ParseEventTimeUs(const CThostFtdcDepthMarketDataField& data) {
    const auto date = ctp::FieldString(data.ActionDay);
    const auto clock = ctp::FieldString(data.UpdateTime);
    int year = 0, month = 0, day = 0, hour = 0, minute = 0, second = 0;
    if (!ParseDay(date, year, month, day) || !ParseClock(clock, hour, minute, second) ||
        data.UpdateMillisec < 0 || data.UpdateMillisec > 999) return std::nullopt;
    constexpr std::int64_t shanghai_offset_seconds = 8 * 60 * 60;
    const auto seconds = DaysFromCivil(year, static_cast<unsigned>(month), static_cast<unsigned>(day)) * 86400
        + hour * 3600 + minute * 60 + second - shanghai_offset_seconds;
    return seconds * 1'000'000 + static_cast<std::int64_t>(data.UpdateMillisec) * 1000;
}

AlignedBarAggregator::AlignedBarAggregator(const std::vector<std::string>& instruments)
    : universe_(instruments.begin(), instruments.end()) {
    for (const auto& id : universe_) stats_.instruments.emplace(id, InstrumentAggregationStats{});
}

bool AlignedBarAggregator::IsContinuityBreak(const std::set<std::string>& reasons) {
    static const std::set<std::string> breaks = {
        "reconnect", "invalid_event_time", "event_time_regression", "late_event"
    };
    return std::any_of(reasons.begin(), reasons.end(), [&](const auto& value) { return breaks.count(value); });
}

std::string AlignedBarAggregator::ReasonsJson(const std::set<std::string>& reasons) {
    std::ostringstream output;
    output << '[';
    bool first = true;
    for (const auto& reason : reasons) {
        if (!first) output << ',';
        first = false;
        output << std::quoted(reason);
    }
    output << ']';
    return output.str();
}

void AlignedBarAggregator::MarkNextAffected(Stream& stream, std::int64_t after_bucket_us, const std::string& reason) {
    auto it = stream.buckets.upper_bound(after_bucket_us);
    if (it == stream.buckets.end()) stream.pending_reasons.insert(reason);
    else it->second.reasons.insert(reason);
}

bool AlignedBarAggregator::Receive(const CThostFtdcDepthMarketDataField& data, std::int64_t received_us) {
    const auto trading_day = ctp::FieldString(data.TradingDay);
    const auto instrument = ctp::FieldString(data.InstrumentID);
    std::lock_guard<std::mutex> lock(mutex_);
    if (!ValidTradingDay(trading_day)) { ++stats_.invalid_trading_day; return false; }
    if (!universe_.count(instrument)) { ++stats_.unknown_instrument; return false; }

    auto& instrument_stats = stats_.instruments.at(instrument);
    const auto parsed = ParseEventTimeUs(data);
    auto& stream = streams_[{trading_day, instrument}];
    if (!parsed) {
        ++stats_.invalid_event_time;
        ++instrument_stats.invalid_event_time;
        if (stream.buckets.empty() || received_us >= stream.buckets.rbegin()->first + kBarIntervalUs + kCloseGraceUs)
            stream.pending_reasons.insert("invalid_event_time");
        else
            stream.buckets.rbegin()->second.reasons.insert("invalid_event_time");
        return false;
    }

    const auto event_us = *parsed;
    const auto bucket_start_us = FloorBucket(event_us);
    const auto bucket_end_us = bucket_start_us + kBarIntervalUs;
    if (bucket_start_us < stream.sealed_through_us || received_us >= bucket_end_us + kCloseGraceUs) {
        ++stats_.late_callbacks;
        ++instrument_stats.late_callbacks;
        MarkNextAffected(stream, bucket_start_us, "late_event");
        return false;
    }

    auto& bucket = stream.buckets[bucket_start_us];
    if (!stream.seen_event) {
        bucket.reasons.insert("collector_start");
        bucket.reasons.insert("trading_day_init");
        stream.seen_event = true;
    }
    auto pending = pending_by_instrument_.find(instrument);
    if (pending != pending_by_instrument_.end()) {
        bucket.reasons.insert(pending->second.begin(), pending->second.end());
        pending_by_instrument_.erase(pending);
    }
    bucket.reasons.insert(stream.pending_reasons.begin(), stream.pending_reasons.end());
    stream.pending_reasons.clear();
    if (stream.latest_event_us && event_us < stream.latest_event_us) {
        bucket.reasons.insert("event_time_regression");
        ++stats_.event_time_regressions;
    }
    stream.latest_event_us = std::max(stream.latest_event_us, event_us);
    bucket.events.push_back(Event{data, event_us, received_us, ++sequence_});
    ++stats_.callbacks_accepted;
    stats_.last_received_us = received_us;
    ++instrument_stats.callbacks_accepted;
    instrument_stats.last_received_us = received_us;
    return true;
}

MarketBar AlignedBarAggregator::Finalize(Stream& stream, std::int64_t bucket_start_us, Bucket bucket) {
    std::stable_sort(bucket.events.begin(), bucket.events.end(), [](const Event& left, const Event& right) {
        return std::tie(left.event_us, left.sequence) < std::tie(right.event_us, right.sequence);
    });
    if (IsContinuityBreak(bucket.reasons)) {
        stream.volume_baseline.reset();
        stream.turnover_baseline.reset();
    }

    MarketBar bar;
    bar.bucket_start_us = bucket_start_us;
    bar.bucket_end_us = bucket_start_us + kBarIntervalUs;
    bar.callback_count = static_cast<std::int64_t>(bucket.events.size());
    bar.close_facts = bucket.events.back().facts;
    bar.first_event_us = bucket.events.front().event_us;
    bar.last_event_us = bucket.events.back().event_us;
    bar.first_received_us = bar.last_received_us = bucket.events.front().received_us;
    for (const auto& event : bucket.events) {
        bar.first_received_us = std::min(bar.first_received_us, event.received_us);
        bar.last_received_us = std::max(bar.last_received_us, event.received_us);
        const double price = event.facts.LastPrice;
        if (!ValidNumber(price) || price <= 0) continue;
        if (!bar.bar_open) bar.bar_open = price;
        bar.bar_close = price;
        bar.bar_high = bar.bar_high ? std::max(*bar.bar_high, price) : price;
        bar.bar_low = bar.bar_low ? std::min(*bar.bar_low, price) : price;
        ++bar.valid_last_price_count;
    }
    bar.close_received_us = bucket.events.back().received_us;

    const auto volume = bar.close_facts.Volume;
    if (!ValidVolume(volume)) bucket.reasons.insert("volume_counter_invalid");
    else if (!stream.volume_baseline) bucket.reasons.insert("volume_baseline_missing");
    else if (volume < *stream.volume_baseline) bucket.reasons.insert("volume_counter_reset");
    else bar.bar_volume = static_cast<std::int64_t>(volume) - *stream.volume_baseline;
    if (ValidVolume(volume)) stream.volume_baseline = volume;
    else stream.volume_baseline.reset();

    const auto turnover = bar.close_facts.Turnover;
    if (!ValidTurnover(turnover)) bucket.reasons.insert("turnover_counter_invalid");
    else if (!stream.turnover_baseline) bucket.reasons.insert("turnover_baseline_missing");
    else if (turnover < *stream.turnover_baseline) bucket.reasons.insert("turnover_counter_reset");
    else bar.bar_turnover = turnover - *stream.turnover_baseline;
    if (ValidTurnover(turnover)) stream.turnover_baseline = turnover;
    else stream.turnover_baseline.reset();

    bar.is_partial = !bucket.reasons.empty();
    bar.partial_reasons = ReasonsJson(bucket.reasons);
    stream.sealed_through_us = std::max(stream.sealed_through_us, bar.bucket_end_us);
    return bar;
}

std::vector<MarketBar> AlignedBarAggregator::CloseEligible(std::int64_t now_us) {
    std::vector<MarketBar> result;
    std::lock_guard<std::mutex> lock(mutex_);
    for (auto& item : streams_) {
        auto& stream = item.second;
        auto it = stream.buckets.begin();
        while (it != stream.buckets.end() && it->first + kBarIntervalUs + kCloseGraceUs <= now_us) {
            const auto start = it->first;
            auto bucket = std::move(it->second);
            it = stream.buckets.erase(it);
            result.push_back(Finalize(stream, start, std::move(bucket)));
        }
    }
    std::sort(result.begin(), result.end(), [](const MarketBar& left, const MarketBar& right) {
        return std::make_tuple(ctp::FieldString(left.close_facts.TradingDay),
                              ctp::FieldString(left.close_facts.InstrumentID), left.bucket_start_us) <
               std::make_tuple(ctp::FieldString(right.close_facts.TradingDay),
                               ctp::FieldString(right.close_facts.InstrumentID), right.bucket_start_us);
    });
    return result;
}

std::optional<std::int64_t> AlignedBarAggregator::ShutdownGraceDeadline(std::int64_t now_us) const {
    std::optional<std::int64_t> result;
    std::lock_guard<std::mutex> lock(mutex_);
    for (const auto& item : streams_) for (const auto& bucket : item.second.buckets) {
        const auto end = bucket.first + kBarIntervalUs;
        const auto deadline = end + kCloseGraceUs;
        if (end <= now_us && now_us < deadline) result = std::max(result.value_or(deadline), deadline);
    }
    return result;
}

void AlignedBarAggregator::MarkReconnect(std::int64_t now_us) {
    constexpr const char* reason = "reconnect";
    std::lock_guard<std::mutex> lock(mutex_);
    for (const auto& instrument : universe_) {
        bool marked = false;
        for (auto& item : streams_) {
            if (item.first.second != instrument) continue;
            auto& stream = item.second;
            for (auto& bucket : stream.buckets) {
                const auto end = bucket.first + kBarIntervalUs;
                if (bucket.first <= now_us && now_us < end + kCloseGraceUs) {
                    bucket.second.reasons.insert(reason);
                    marked = true;
                }
            }
        }
        if (!marked) pending_by_instrument_[instrument].insert(reason);
    }
}

AggregationStats AlignedBarAggregator::Stats() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return stats_;
}

} // namespace collector
