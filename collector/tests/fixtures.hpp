#pragma once
#include "domain/market.hpp"
inline CThostFtdcDepthMarketDataField Tick(const std::string& day = "20260904", const std::string& id = "IF2609") {
    CThostFtdcDepthMarketDataField tick{};
    ctp::CopyField(tick.TradingDay, day);
    ctp::CopyField(tick.ActionDay, "20260903");
    ctp::CopyField(tick.InstrumentID, id);
    ctp::CopyField(tick.ExchangeID, "CFFEX");
    ctp::CopyField(tick.UpdateTime, "09:31:01");
    tick.UpdateMillisec = 500;
    tick.LastPrice = 4000.2;
    tick.Volume = 23;
    tick.Turnover = 2300;
    tick.AskPrice5 = std::numeric_limits<double>::max();
    return tick;
}
