#pragma once
#include "fixtures.hpp"
#include <functional>

// This is a test double, never built into the production executable.
struct FakeApi : CThostFtdcMdApi {
    virtual ~FakeApi() = default;
    CThostFtdcMdSpi* spi = nullptr;
    int login_result = 0, subscribe_result = 0, login_calls = 0, subscription_calls = 0, last_login_id = 0;
    bool auto_respond = false, delete_on_release = false, subscribed = false;
    bool* released = nullptr;
    std::vector<std::string> requested;
    void Release() override { if (released) *released = spi == nullptr; if (delete_on_release) delete this; }
    void Init() override { if (spi) spi->OnFrontConnected(); }
    int Join() override { return 0; }
    const char* GetTradingDay() override { return "20260904"; }
    void RegisterFront(char*) override {}
    void RegisterNameServer(char*) override {}
    void RegisterFensUserInfo(CThostFtdcFensUserInfoField*) override {}
    void RegisterSpi(CThostFtdcMdSpi* value) override {
        if (!value && spi && auto_respond && subscribed) {
            auto tail = Tick(); tail.Volume = 99;
            spi->OnRtnDepthMarketData(&tail); // Last accepted callback before unregister.
        }
        spi = value;
    }
    int ReqUserLogin(CThostFtdcReqUserLoginField*, int id) override {
        ++login_calls; last_login_id = id;
        if (auto_respond && login_result == 0) Login();
        return login_result;
    }
    void Login(int error = 0) {
        CThostFtdcRspUserLoginField response{}; ctp::CopyField(response.TradingDay, "20260904");
        CThostFtdcRspInfoField info{}; info.ErrorID = error;
        spi->OnRspUserLogin(&response, &info, last_login_id, true);
    }
    void SubscriptionReply(const std::string& id, int error = 0) {
        CThostFtdcSpecificInstrumentField instrument{}; ctp::CopyField(instrument.InstrumentID, id);
        CThostFtdcRspInfoField info{}; info.ErrorID = error;
        spi->OnRspSubMarketData(&instrument, &info, 0, true);
    }
    int SubscribeMarketData(char* ids[], int count) override {
        ++subscription_calls; requested.clear();
        for (int i = 0; i < count; ++i) {
            requested.emplace_back(ids[i]);
            if (auto_respond && subscribe_result == 0) {
                SubscriptionReply(ids[i]); auto tick = Tick("20260904", ids[i]); spi->OnRtnDepthMarketData(&tick);
                subscribed = true;
            }
        }
        return subscribe_result;
    }
    int UnSubscribeMarketData(char*[], int) override { return 0; }
    int SubscribeForQuoteRsp(char*[], int) override { return 0; }
    int UnSubscribeForQuoteRsp(char*[], int) override { return 0; }
    int ReqUserLogout(CThostFtdcUserLogoutField*, int) override { return 0; }
    int ReqQryMulticastInstrument(CThostFtdcQryMulticastInstrumentField*, int) override { return 0; }
};
