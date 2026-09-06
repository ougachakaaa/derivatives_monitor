#pragma once
#include "config.hpp"
#include "market.hpp"
#include <atomic>

namespace collector {
inline std::int64_t SteadyMs() {
    return std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count();
}
enum class Subscription { NotSent, Pending, Subscribed, Failed };
inline const char* SubscriptionName(Subscription value) {
    switch (value) {
        case Subscription::NotSent: return "not_sent";
        case Subscription::Pending: return "pending";
        case Subscription::Subscribed: return "subscribed";
        case Subscription::Failed: return "failed";
    }
    return "unknown";
}
struct InstrumentStatus {
    Subscription subscription = Subscription::NotSent;
    int error_id = 0;
    std::int64_t deadline_ms = 0, last_received_us = 0;
    std::uint64_t received = 0;
};
struct SessionStatus {
    bool connected = false, logged_in = false, ever_logged_in = false;
    std::uint64_t connections = 0, disconnections = 0;
    std::string login_day;
    std::map<std::string, InstrumentStatus> instruments;
};

class CtpSession final : public CThostFtdcMdSpi {
public:
    CtpSession(CThostFtdcMdApi& api, const Config& config, MarketState& market, std::string run_id)
        : api_(api), config_(config), market_(market), run_id_(std::move(run_id)) {
        for (const auto& id : config.instruments) status_.instruments.emplace(id, InstrumentStatus{});
    }
    void OnFrontConnected() override;
    void OnFrontDisconnected(int reason) override;
    void OnHeartBeatWarning(int elapsed) override;
    void OnRspUserLogin(CThostFtdcRspUserLoginField*, CThostFtdcRspInfoField*, int, bool) override;
    void OnRspSubMarketData(CThostFtdcSpecificInstrumentField*, CThostFtdcRspInfoField*, int, bool) override;
    void OnRspError(CThostFtdcRspInfoField*, int, bool) override;
    void OnRtnDepthMarketData(CThostFtdcDepthMarketDataField*) override;
    void Pump(std::int64_t now_ms = SteadyMs());
    SessionStatus Status() const { std::lock_guard<std::mutex> lock(mutex_); return status_; }
    void CheckFailure() const {
        if (failed_) { std::lock_guard<std::mutex> lock(mutex_); throw std::runtime_error("CTP callback failed: " + failure_); }
    }
private:
    template<class F> void Callback(F&& f) noexcept {
        try { f(); }
        catch (const std::exception& error) {
            try { std::lock_guard<std::mutex> lock(mutex_); failure_ = error.what(); } catch (...) {}
            failed_ = true;
        } catch (...) { failed_ = true; }
    }
    template<class... Args> void Log(Args&&... args) {
        ctp::Log("utc_us=", NowUs(), " run_id=", run_id_, " ", std::forward<Args>(args)...);
    }
    CThostFtdcMdApi& api_;
    const Config config_;
    MarketState& market_;
    const std::string run_id_;
    mutable std::mutex mutex_;
    SessionStatus status_;
    bool login_pending_ = false;
    int request_id_ = 0, active_login_id_ = 0;
    std::int64_t login_deadline_ms_ = 0, next_login_ms_ = 0, next_subscription_ms_ = 0;
    std::atomic<bool> failed_{false};
    std::string failure_;
};
} // namespace collector
