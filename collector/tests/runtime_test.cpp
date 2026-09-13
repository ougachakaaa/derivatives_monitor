#include "app/runtime.hpp"
#include "fake_api.hpp"
#include "sqlite_test.hpp"

#include <ctime>

namespace {
CThostFtdcDepthMarketDataField CurrentTick() {
    auto tick = Tick();
    const auto now = std::time(nullptr) + 8 * 60 * 60;
    std::tm local{};
    gmtime_r(&now, &local);
    char day[9] = {}, clock[9] = {};
    std::strftime(day, sizeof(day), "%Y%m%d", &local);
    std::strftime(clock, sizeof(clock), "%H:%M:%S", &local);
    ctp::CopyField(tick.TradingDay, day);
    ctp::CopyField(tick.ActionDay, day);
    ctp::CopyField(tick.UpdateTime, clock);
    tick.UpdateMillisec = 0;
    return tick;
}
}

int main() {
    using namespace collector;
    {
        Config batch_config;
        batch_config.subscription_batch_size = 100;
        for (int i = 0; i < 205; ++i) batch_config.instruments.push_back("IO2609-C-" + std::to_string(3000 + i * 50));
        AlignedBarAggregator batch_state(batch_config.instruments);
        FakeApi batch_api;
        CtpSession batch(batch_api, batch_config, batch_state, "TEST DOUBLE - batches");
        batch_api.RegisterSpi(&batch); batch_api.Init();
        const auto start = SteadyMs(); batch.Pump(start); batch_api.Login();
        batch.Pump(start + 1); CHECK(batch_api.requested.size() == 100);
        const auto failed_id = batch_api.requested.front();
        for (const auto& id : batch_api.requested) batch_api.SubscriptionReply(id, id == failed_id ? 31 : 0);
        batch.Pump(start + 999); CHECK(batch_api.subscription_calls == 1);
        batch.Pump(start + 1001); CHECK(batch_api.requested.size() == 100);
        for (const auto& id : batch_api.requested) batch_api.SubscriptionReply(id);
        batch.Pump(start + 2001); CHECK(batch_api.requested.size() == 5);
        for (const auto& id : batch_api.requested) batch_api.SubscriptionReply(id);
        std::size_t subscribed = 0;
        for (const auto& item : batch.Status().instruments) subscribed += item.second.subscription == Subscription::Subscribed;
        CHECK(subscribed == 204);
        CHECK(batch.Status().instruments.at(failed_id).subscription == Subscription::Failed);
        batch.OnFrontDisconnected(1); batch.OnFrontConnected(); batch.Pump(start + 3000); batch_api.Login();
        batch.Pump(start + 3001); CHECK(batch_api.requested.size() == 100);
    }

    Config config;
    config.instruments = {"IF2609", "IO2609-C-4000"};
    config.connect_timeout_seconds = 2;
    config.retry_interval_seconds = 1;
    config.subscription_batch_size = 1;
    AlignedBarAggregator state(config.instruments);
    FakeApi api;
    CtpSession session(api, config, state, "TEST DOUBLE - session");
    api.RegisterSpi(&session);
    auto now = SteadyMs();
    session.Pump(now); CHECK(api.login_calls == 0);
    api.Init(); api.login_result = -2;
    session.Pump(now); CHECK(api.login_calls == 1);
    session.Pump(now + 999); CHECK(api.login_calls == 1);
    api.login_result = 0; session.Pump(now + 1000); CHECK(api.login_calls == 2);
    api.Login(7); CHECK(!session.Status().logged_in);
    session.Pump(now + 2000); api.Login(); CHECK(session.Status().logged_in);
    api.subscribe_result = -2; session.Pump(now + 2001);
    CHECK(session.Status().instruments.at("IF2609").subscription == Subscription::NotSent);
    api.subscribe_result = 0; session.Pump(now + 3001);
    api.SubscriptionReply("IF2609");
    auto tick = CurrentTick();
    api.spi->OnRtnDepthMarketData(&tick);
    CHECK(session.Status().instruments.at("IF2609").received == 1);
    CHECK(state.Stats().callbacks_accepted == 1);
    session.OnFrontDisconnected(0x1001);
    CHECK(!session.Status().connected && !session.Status().logged_in);
    session.OnFrontConnected(); session.Pump(now + 4001); api.Login();
    session.Pump(now + 4002); api.SubscriptionReply("IF2609");
    CHECK(session.Status().connections == 2 && session.Status().disconnections == 1);

    // Uncorrelated zero request IDs are accepted only while a login is actually pending.
    AlignedBarAggregator zero_state({"IF2609"});
    FakeApi zero_api;
    CtpSession zero_session(zero_api, config, zero_state, "TEST DOUBLE - zero-id");
    zero_api.RegisterSpi(&zero_session);
    CThostFtdcRspUserLoginField response{}; ctp::CopyField(response.TradingDay, "20260907");
    CThostFtdcRspInfoField info{};
    zero_api.Init();
    zero_session.OnRspUserLogin(&response, &info, 0, true);
    CHECK(!zero_session.Status().logged_in);
    zero_session.Pump(SteadyMs());
    zero_session.OnRspUserLogin(&response, &info, 0, true);
    CHECK(zero_session.Status().logged_in);

    {
        TempDirectory temp;
        config.data_directory = temp.path / "data";
        config.flow_path = temp.path / "flow";
        config.front = "test-double";
        config.instruments = {"IF2609"};
        config.run_seconds = 1;
        bool released = false;
        auto* fake = new FakeApi;
        fake->auto_respond = true; fake->delete_on_release = true; fake->released = &released;
        volatile std::sig_atomic_t stop = 0;
        CHECK(RunCollector(config, stop, ApiPtr(fake)) == 0);
        CHECK(released);
        std::ifstream health(config.data_directory / ".collector-status.json");
        const std::string json((std::istreambuf_iterator<char>(health)), {});
        CHECK(json.find("\"schema_version\": 2") != std::string::npos);
        CHECK(json.find("\"process_state\": \"stopped\"") != std::string::npos);
        CHECK(json.find("\"late_callbacks\": 2") != std::string::npos);
        CHECK(!std::filesystem::exists(config.data_directory / "20260904.sqlite"));
    }
}
