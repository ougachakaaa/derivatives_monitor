#include "fake_api.hpp"
#include <atomic>
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
                            auto tick = Tick(step < 20 ? "20260904" : "20260907");
                            tick.Volume = step;
                            spi->OnRtnDepthMarketData(&tick);
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
        for (int i = 0; i < count; ++i) SubscriptionReply(ids[i]);
        subscribed = true; return 0;
    }
private:
    std::mutex mutex_;
    std::atomic<bool> running_{false};
    std::thread worker_;
};
} // namespace
CThostFtdcMdApi* CThostFtdcMdApi::CreateFtdcMdApi(const char*, bool, bool, bool) { return new StreamingApi; }
const char* CThostFtdcMdApi::GetApiVersion() { return "TEST DOUBLE - synthetic market data"; }
