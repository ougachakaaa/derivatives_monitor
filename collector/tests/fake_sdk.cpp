#include "fake_api.hpp"
#include <atomic>
#include <cstdlib>
#include <thread>

namespace {
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
                    if (spi) {
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
                                auto tick = Tick(step < 20 ? "20260904" : "20260907");
                                tick.Volume = step;
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
    const bool night_ = std::getenv("DM_TEST_SCENARIO") && std::string(std::getenv("DM_TEST_SCENARIO")) == "shfe-night";
    std::set<std::string> targets_;
    std::mutex mutex_;
    std::atomic<bool> running_{false};
    std::thread worker_;
};
} // namespace
CThostFtdcMdApi* CThostFtdcMdApi::CreateFtdcMdApi(const char*, bool, bool, bool) { return new StreamingApi; }
const char* CThostFtdcMdApi::GetApiVersion() { return "TEST DOUBLE - synthetic market data"; }
