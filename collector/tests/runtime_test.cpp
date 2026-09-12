#include "runtime.hpp"
#include "fake_api.hpp"
#include "sqlite_test.hpp"

int main() {
    using namespace collector;
    {
        Config batch_config; batch_config.subscription_batch_size = 100;
        for (int i = 0; i < 205; ++i) batch_config.instruments.push_back("IO2609-C-" + std::to_string(3000 + i * 50));
        MarketSnapshotBuffer batch_state(batch_config.instruments); FakeApi batch_api;
        CtpSession batch(batch_api, batch_config, batch_state, "test-double-batches");
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
        CHECK(batch_api.subscription_calls == 4);
    }
    Config config;
    config.instruments = {"IF2609", "IO2609-C-4000"};
    config.connect_timeout_seconds = 2; config.retry_interval_seconds = 1; config.subscription_batch_size = 1;
    MarketSnapshotBuffer state(config.instruments);
    FakeApi api;
    CtpSession session(api, config, state, "test-double"); api.RegisterSpi(&session);
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
    CHECK(api.requested == std::vector<std::string>{"IF2609"});
    api.SubscriptionReply("IF2609");
    session.Pump(now + 4001); api.SubscriptionReply("IO2609-C-4000", 31);
    CHECK(session.Status().instruments.at("IF2609").subscription == Subscription::Subscribed);
    CHECK(session.Status().instruments.at("IF2609").received == 0);
    CHECK(session.Status().instruments.at("IO2609-C-4000").subscription == Subscription::Failed);
    auto tick = Tick(); api.spi->OnRtnDepthMarketData(&tick);
    CHECK(session.Status().instruments.at("IF2609").received == 1);
    session.OnFrontDisconnected(0x1001);
    CHECK(!session.Status().connected && !session.Status().logged_in);
    CHECK(state.Materialize(NowUs()).size() == 1); // Disconnect cannot discard pending facts.
    session.OnFrontConnected(); session.Pump(now + 5000); api.Login();
    session.Pump(now + 5001); api.SubscriptionReply("IF2609");
    session.Pump(now + 6001); session.Pump(now + 8002); // missing second subscription response
    CHECK(session.Status().instruments.at("IO2609-C-4000").subscription == Subscription::Failed);
    CHECK(session.Status().connections == 2 && session.Status().disconnections == 1);
    // Late login response after disconnect must not restore a dead session.
    session.OnFrontDisconnected(1); api.Login(); CHECK(!session.Status().logged_in);
    session.OnFrontConnected(); session.Pump(now + 9000);
    const int calls = api.login_calls;
    session.Pump(now + 11001); CHECK(api.login_calls == calls);
    session.Pump(now + 12001); CHECK(api.login_calls == calls + 1);
    CThostFtdcRspInfoField error{}; error.ErrorID = 8;
    session.OnRspError(&error, api.last_login_id, true);
    session.Pump(now + 13002); CHECK(api.login_calls == calls + 2);
    api.Login(); session.Pump(now + 13003);
    // Callback exceptions are captured, never propagated through the SDK boundary.
    auto day1 = Tick("20260907"), day2 = Tick("20260908"), day3 = Tick("20260909");
    api.spi->OnRtnDepthMarketData(&day1); api.spi->OnRtnDepthMarketData(&day2); api.spi->OnRtnDepthMarketData(&day3);
    Throws([&] { session.CheckFailure(); });
    {
        MarketSnapshotBuffer zero_state(config.instruments);
        FakeApi zero_api;
        CtpSession zero_session(zero_api, config, zero_state, "test-double-zero-id");
        zero_api.RegisterSpi(&zero_session);
        CThostFtdcRspUserLoginField response{};
        ctp::CopyField(response.TradingDay, "20260907");
        CThostFtdcRspInfoField info{};
        zero_api.Init();
        zero_session.OnRspUserLogin(&response, &info, 0, true);
        CHECK(!zero_session.Status().logged_in); // No pending request.
        zero_session.Pump(SteadyMs());
        zero_session.OnRspUserLogin(&response, &info, zero_api.last_login_id + 1, true);
        CHECK(!zero_session.Status().logged_in); // Nonzero mismatches remain invalid.
        zero_session.OnRspUserLogin(&response, &info, 0, false);
        CHECK(!zero_session.Status().logged_in);
        zero_session.OnRspUserLogin(&response, &info, 0, true);
        CHECK(zero_session.Status().logged_in);
        CHECK(zero_session.Status().login_day == "20260907");
        zero_session.Pump(SteadyMs());
        CHECK(zero_api.subscription_calls == 1);
        zero_session.OnFrontDisconnected(1);
        zero_session.OnRspUserLogin(&response, &info, 0, true);
        CHECK(!zero_session.Status().logged_in);
    }
    {
        TempDirectory temp;
        config.data_directory = temp.path / "data"; config.flow_path = temp.path / "flow";
        config.front = "test-double"; config.instruments = {"IF2609"};
        config.snapshot_interval_ms = 50; config.run_seconds = 1;
        bool released = false; auto* fake = new FakeApi;
        fake->auto_respond = true; fake->delete_on_release = true; fake->released = &released;
        volatile std::sig_atomic_t stop = 0;
        CHECK(RunCollector(config, stop, ApiPtr(fake)) == 0);
        CHECK(released);
        std::ifstream health(config.data_directory / ".collector-status.json");
        const std::string health_json((std::istreambuf_iterator<char>(health)), {});
        CHECK(health_json.find("\"process_state\": \"stopped\"") != std::string::npos);
        TestDb db(config.data_directory / "20260904.sqlite");
        CHECK(db.Scalar("SELECT count(*) FROM snapshots") == "2");
        CHECK(db.Scalar("SELECT Volume FROM snapshots ORDER BY id DESC LIMIT 1") == "99");
        CHECK(db.Scalar("SELECT stopped_us IS NOT NULL FROM runs") == "1");
        CHECK(db.Scalar("PRAGMA integrity_check") == "ok");
    }
    {
        TempDirectory temp;
        config.data_directory = temp.path / "data"; config.flow_path = temp.path / "flow";
        std::filesystem::create_directories(config.data_directory / "20260904.sqlite");
        bool released = false; auto* fake = new FakeApi;
        fake->auto_respond = true; fake->delete_on_release = true; fake->released = &released;
        volatile std::sig_atomic_t stop = 0;
        Throws([&] { RunCollector(config, stop, ApiPtr(fake)); });
        CHECK(released);
        std::ifstream health(config.data_directory / ".collector-status.json");
        const std::string health_json((std::istreambuf_iterator<char>(health)), {});
        CHECK(health_json.find("\"process_state\": \"failed\"") != std::string::npos);
    }
}
