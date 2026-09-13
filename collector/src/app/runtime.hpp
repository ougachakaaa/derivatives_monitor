#pragma once

#include "ingestion/session.hpp"

#include <csignal>
#include <memory>

namespace collector {

struct ReleaseApi {
    void operator()(CThostFtdcMdApi* api) const { if (api) api->Release(); }
};
using ApiPtr = std::unique_ptr<CThostFtdcMdApi, ReleaseApi>;

// Optional ownership injection is restricted to TEST DOUBLE executables.
int RunCollector(const Config& config, const volatile std::sig_atomic_t& stop, ApiPtr api = {});

} // namespace collector
