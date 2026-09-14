#include "fake_api.hpp"
#include <atomic>
#include <cstdlib>
#include <ctime>
#include <thread>

namespace {
void UseCurrentEventTime(CThostFtdcDepthMarketDataField& tick, const char* trading_day, int step) {
    const auto now = std::time(nullptr) + 8 * 60 * 60;
    std::tm local{};
    gmtime_r(&now, &local);
    char action_day[9] = {}, clock[9] = {};
    std::strftime(action_day, sizeof(action_day), "%Y%m%d", &local);
    std::strftime(clock, sizeof(clock), "%H:%M:%S", &local);
    ctp::CopyField(tick.TradingDay, trading_day && *trading_day ? trading_day : action_day);
    ctp::CopyField(tick.ActionDay, action_day);
    ctp::CopyField(tick.UpdateTime, clock);
    tick.UpdateMillisec = (step * 50) % 1000;
}

class StreamingApi final : public FakeApi {
public:
    ~StreamingApi() override { running_ = false; if (worker_.joinable()) worker_.join(); }
    void Release() override { delete this; }
    void RegisterSpi(CThostFtdcMdSpi* value) override {
        std::lock_guard<std::mutex> lock(mutex_); spi = value;
    }
    void Init() override {
        running_ = true;
        worker_ = std::thread([&] {
            for (int step = 0; running_; ++step) {
                {
                    std::lock_guard<std::mutex> lock(mutex_);
                    if (spi && !no_front_) {
                        if (step == 0 || step == 12) spi->OnFrontConnected();
                        if (step == 10) { subscribed = false; spi->OnFrontDisconnected(0x1001); }
                        if (subscribed) {
                            if (night_) {
                                for (const auto& id : targets_) {
                                    const bool metal = id.rfind("au", 0) == 0 || id.rfind("ag", 0) == 0;
                                    if (!metal && (step < 25 || step >= 35)) continue;
                                    auto tick = Tick(step < 35 ? "20260908" : "20260909", id);
                                    ctp::CopyField(tick.ExchangeID, metal ? "SHFE" : "CFFEX");
                                    ctp::CopyField(tick.ActionDay, step < 15 ? "20260907" : "20260908");
                                    const char* time = step < 10 ? "21:00:00" : step < 15 ? "23:59:59" :
                                        step < 20 ? "00:00:00" : step < 25 ? "02:29:59" :
                                        step < 30 ? "09:00:00" : step < 35 ? "14:59:59" : "21:00:00";
                                    ctp::CopyField(tick.UpdateTime, time);
                                    tick.Volume = step;
                                    spi->OnRtnDepthMarketData(&tick);
                                }
                            } else {
                                const char* day = step < 20 ? std::getenv("DM_TEST_DAY1") : std::getenv("DM_TEST_DAY2");
                                auto tick = Tick();
                                UseCurrentEventTime(tick, day, step);
                                tick.Volume = step;
                                tick.Turnover = step * 100.0;
                                spi->OnRtnDepthMarketData(&tick);
                            }
                        }
                    }
                }
                std::this_thread::sleep_for(std::chrono::milliseconds(50));
            }
        });
    }
    int ReqUserLogin(CThostFtdcReqUserLoginField*, int id) override {
        std::lock_guard<std::mutex> lock(mutex_);
        last_login_id = id; Login(); return 0;
    }
    int SubscribeMarketData(char* ids[], int count) override {
        std::lock_guard<std::mutex> lock(mutex_);
        for (int i = 0; i < count; ++i) { targets_.insert(ids[i]); SubscriptionReply(ids[i]); }
        subscribed = true; return 0;
    }
private:
    const bool no_front_ = std::getenv("DM_TEST_SCENARIO") && std::string(std::getenv("DM_TEST_SCENARIO")) == "no-front";
    const bool night_ = std::getenv("DM_TEST_SCENARIO") && std::string(std::getenv("DM_TEST_SCENARIO")) == "shfe-night";
    std::set<std::string> targets_;
    std::mutex mutex_;
    std::atomic<bool> running_{false};
    std::thread worker_;
};
} // namespace
CThostFtdcMdApi* CThostFtdcMdApi::CreateFtdcMdApi(const char*, bool, bool, bool) { return new StreamingApi; }
const char* CThostFtdcMdApi::GetApiVersion() { return "TEST DOUBLE - synthetic market data"; }
