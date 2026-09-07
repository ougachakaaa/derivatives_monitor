#include "runtime.hpp"
#include "fake_api.hpp"
#include "sqlite_test.hpp"
#include <exception>
#include <thread>

// Real runtime clock, synthetic API only. No production scheduler/test clock hooks.
class WindowApi final : public FakeApi {
public:
    explicit WindowApi(const std::filesystem::path& directory, std::exception_ptr& failure)
        : directory_(directory), failure_(failure) { auto_respond = true; }
    ~WindowApi() override { if (worker_.joinable()) worker_.join(); }
    void Release() override { delete this; }
    void RegisterSpi(CThostFtdcMdSpi* value) override {
        std::lock_guard<std::mutex> lock(mutex_);
        FakeApi::RegisterSpi(value); // Emits Volume=99 just before unregistering.
    }
    int ReqUserLogin(CThostFtdcReqUserLoginField* request, int id) override {
        std::lock_guard<std::mutex> lock(mutex_);
        return FakeApi::ReqUserLogin(request, id);
    }
    int SubscribeMarketData(char* ids[], int count) override {
        std::lock_guard<std::mutex> lock(mutex_);
        return FakeApi::SubscribeMarketData(ids, count);
    }
    void Init() override {
        FakeApi::Init();
        worker_ = std::thread([this] {
            try {
                const auto start = std::chrono::steady_clock::now();
                const auto at = [&](int seconds) {
                    std::this_thread::sleep_until(start + std::chrono::seconds(seconds));
                };
                const auto heartbeat = [&] {
                    std::ifstream input(directory_ / ".collector-status.json");
                    return std::string((std::istreambuf_iterator<char>(input)), {});
                };
                at(3);
                CHECK(heartbeat().find("\"accepted\": 1,") != std::string::npos);
                for (int i = 1; i <= 2; ++i) {
                    at(i * 4);
                    std::lock_guard<std::mutex> lock(mutex_);
                    CHECK(spi && subscribed);
                    auto tick = Tick(); tick.Volume = 40 + i; tick.LastPrice = 4100 + i;
                    ctp::CopyField(tick.UpdateTime, "09:30:59");
                    spi->OnRtnDepthMarketData(&tick);
                }
                at(12);
                CHECK(heartbeat().find("\"accepted\": 3,") != std::string::npos);
                CHECK(!std::filesystem::exists(directory_ / "20260904.sqlite"));
                at(18);
                TestDb db(directory_ / "20260904.sqlite");
                CHECK(db.Scalar("SELECT count(*) FROM snapshots") == "1");
                CHECK(db.Scalar("SELECT Volume FROM snapshots") == "42");
                CHECK(db.Scalar("SELECT LastPrice FROM snapshots") == "4102.0");
                CHECK(db.Scalar("SELECT sequence FROM snapshots") == "3");
                CHECK(db.Scalar("SELECT UpdateTime FROM snapshots") == "09:30:59");
                CHECK(db.Scalar("SELECT snapshot_us > received_us FROM snapshots") == "1");
                CHECK(db.Scalar("SELECT snapshot_interval_ms FROM runs") == "15000");
                at(32); // Second scheduled materialization had no new callbacks.
                CHECK(db.Scalar("SELECT count(*) FROM snapshots") == "1");
                CHECK(heartbeat().find("\"accepted\": 3,") != std::string::npos);
                CHECK(heartbeat().find("\"written\": 1,") != std::string::npos);
            } catch (...) { failure_ = std::current_exception(); }
        });
    }
private:
    const std::filesystem::path directory_;
    std::exception_ptr& failure_;
    std::mutex mutex_;
    std::thread worker_;
};

int main() {
    using namespace collector;
    TempDirectory temp;
    Config config;
    config.front = "test-double"; config.instruments = {"IF2609"};
    config.data_directory = temp.path / "data"; config.flow_path = temp.path / "flow";
    config.run_seconds = 33;
    CHECK(config.snapshot_interval_ms == 15000);
    std::exception_ptr failure;
    volatile std::sig_atomic_t stop = 0;
    CHECK(RunCollector(config, stop, ApiPtr(new WindowApi(config.data_directory, failure))) == 0);
    if (failure) std::rethrow_exception(failure);
    TestDb db(config.data_directory / "20260904.sqlite");
    CHECK(db.Scalar("SELECT count(*) FROM snapshots") == "2");
    CHECK(db.Scalar("SELECT Volume FROM snapshots ORDER BY id DESC LIMIT 1") == "99");
    CHECK(db.Scalar("SELECT sequence FROM snapshots ORDER BY id DESC LIMIT 1") == "4");
    CHECK(db.Scalar("SELECT stopped_us IS NOT NULL FROM runs") == "1");
    CHECK(db.Scalar("PRAGMA integrity_check") == "ok");
}
