#include "session.hpp"

namespace collector {
void CtpSession::OnFrontConnected() {
    Callback([&] {
        std::lock_guard<std::mutex> lock(mutex_);
        status_.connected = true; status_.logged_in = false; status_.login_day.clear();
        ++status_.connections;
        login_pending_ = false; active_login_id_ = 0; next_login_ms_ = 0;
        for (auto& item : status_.instruments) item.second = {};
        Log("event=front_connected connections=", status_.connections);
    });
}
void CtpSession::OnFrontDisconnected(int reason) {
    Callback([&] {
        std::lock_guard<std::mutex> lock(mutex_);
        status_.connected = false; status_.logged_in = false; status_.login_day.clear();
        ++status_.disconnections;
        login_pending_ = false; active_login_id_ = 0;
        for (auto& item : status_.instruments) item.second = {};
        Log("event=front_disconnected reason=", reason, " disconnections=", status_.disconnections);
    });
}
void CtpSession::OnHeartBeatWarning(int elapsed) {
    Callback([&] { Log("event=heartbeat_warning elapsed_seconds=", elapsed); });
}
void CtpSession::OnRspUserLogin(CThostFtdcRspUserLoginField* response, CThostFtdcRspInfoField* info, int id, bool last) {
    Callback([&] {
        std::lock_guard<std::mutex> lock(mutex_);
        // Some real MD fronts return zero instead of echoing the request ID.
        // Only accept that uncorrelated response while a login is pending.
        if (!last || !status_.connected || !login_pending_ || (id != 0 && id != active_login_id_)) return;
        const int error = info ? info->ErrorID : 0;
        login_pending_ = false;
        status_.logged_in = error == 0 && response != nullptr;
        next_login_ms_ = SteadyMs() + config_.retry_interval_seconds * 1000;
        if (status_.logged_in) {
            status_.ever_logged_in = true;
            status_.login_day = ctp::FieldString(response->TradingDay);
            next_subscription_ms_ = 0;
        }
        Log("event=login_response request_id=", id, " error_id=", error,
            " logged_in=", status_.logged_in, " trading_day=", status_.login_day);
    });
}
void CtpSession::OnRspSubMarketData(CThostFtdcSpecificInstrumentField* instrument, CThostFtdcRspInfoField* info, int, bool) {
    Callback([&] {
        std::lock_guard<std::mutex> lock(mutex_);
        if (!status_.logged_in) return;
        const auto id = instrument ? ctp::FieldString(instrument->InstrumentID) : "";
        const int error = info ? info->ErrorID : 0;
        auto it = status_.instruments.find(id);
        // Subscription calls have no caller-provided request ID. Correlate by exact instrument.
        if (it != status_.instruments.end() && it->second.subscription == Subscription::Pending) {
            it->second.subscription = error == 0 ? Subscription::Subscribed : Subscription::Failed;
            it->second.error_id = error;
        }
        Log("event=subscription_response instrument=", id, " error_id=", error);
    });
}
void CtpSession::OnRspError(CThostFtdcRspInfoField* info, int id, bool last) {
    Callback([&] {
        std::lock_guard<std::mutex> lock(mutex_);
        if (last && login_pending_ && id == active_login_id_) {
            login_pending_ = false; next_login_ms_ = SteadyMs() + config_.retry_interval_seconds * 1000;
        }
        Log("event=error_response request_id=", id, " error_id=", info ? info->ErrorID : 0);
    });
}
void CtpSession::OnRtnDepthMarketData(CThostFtdcDepthMarketDataField* data) {
    const auto received_us = NowUs();
    Callback([&] {
        if (!data) return;
        {
            std::lock_guard<std::mutex> lock(mutex_);
            if (!status_.logged_in) return;
        }
        if (!market_.Receive(*data, received_us)) return;
        std::lock_guard<std::mutex> lock(mutex_);
        auto it = status_.instruments.find(ctp::FieldString(data->InstrumentID));
        if (it != status_.instruments.end()) {
            ++it->second.received; it->second.last_received_us = received_us;
        }
    });
}

void CtpSession::Pump(std::int64_t now_ms) {
    CheckFailure();
    int login_id = 0;
    std::uint64_t connection = 0;
    std::vector<std::string> subscriptions;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        if (!status_.connected) return;
        connection = status_.connections;
        if (!status_.logged_in) {
            if (login_pending_ && now_ms >= login_deadline_ms_) {
                login_pending_ = false;
                next_login_ms_ = now_ms + config_.retry_interval_seconds * 1000;
                Log("event=login_timeout request_id=", active_login_id_);
            }
            if (!login_pending_ && now_ms >= next_login_ms_) {
                login_id = active_login_id_ = ++request_id_; login_pending_ = true;
                login_deadline_ms_ = now_ms + config_.connect_timeout_seconds * 1000;
            }
        } else {
            for (auto& item : status_.instruments) {
                auto& value = item.second;
                if (value.subscription == Subscription::Pending && now_ms >= value.deadline_ms) {
                    value.subscription = Subscription::Failed; value.error_id = -1;
                    Log("event=subscription_timeout instrument=", item.first);
                }
                if (now_ms >= next_subscription_ms_ && value.subscription == Subscription::NotSent &&
                    subscriptions.size() < static_cast<std::size_t>(config_.subscription_batch_size)) {
                    subscriptions.push_back(item.first); value.subscription = Subscription::Pending;
                    value.deadline_ms = now_ms + config_.connect_timeout_seconds * 1000;
                }
            }
            if (!subscriptions.empty()) next_subscription_ms_ = now_ms + 1000;
        }
    }
    // Never hold mutex_ across vendor calls: a test API (or SDK) can respond synchronously.
    if (login_id) {
        CThostFtdcReqUserLoginField request{};
        ctp::CopyField(request.BrokerID, config_.broker_id); ctp::CopyField(request.UserID, config_.user_id);
        ctp::CopyField(request.Password, config_.password); ctp::CopyField(request.UserProductInfo, config_.user_product_info);
        const int result = api_.ReqUserLogin(&request, login_id);
        Log("event=login_request request_id=", login_id, " result=", result);
        if (result != 0) {
            std::lock_guard<std::mutex> lock(mutex_);
            if (status_.connections == connection && active_login_id_ == login_id && login_pending_) {
                login_pending_ = false; next_login_ms_ = now_ms + config_.retry_interval_seconds * 1000;
            }
        }
    }
    if (!subscriptions.empty()) {
        std::vector<char*> ids;
        for (auto& id : subscriptions) ids.push_back(id.data());
        const int result = api_.SubscribeMarketData(ids.data(), static_cast<int>(ids.size()));
        Log("event=subscription_request count=", ids.size(), " result=", result);
        if (result != 0) {
            std::lock_guard<std::mutex> lock(mutex_);
            if (status_.connected && status_.logged_in && status_.connections == connection) {
                for (const auto& id : subscriptions) {
                    auto& value = status_.instruments.at(id);
                    if (value.subscription == Subscription::Pending) {
                        value.subscription = Subscription::NotSent; value.error_id = result;
                    }
                }
                next_subscription_ms_ = now_ms + config_.retry_interval_seconds * 1000;
            }
        }
    }
}
} // namespace collector
