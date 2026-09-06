#pragma once
#include "session.hpp"
#include <csignal>
#include <memory>

namespace collector {
struct ReleaseApi {
    void operator()(CThostFtdcMdApi* api) const { if (api) api->Release(); }
};
using ApiPtr = std::unique_ptr<CThostFtdcMdApi, ReleaseApi>;
// Optional API ownership injection is used only by C++ tests; production creates the vendor API.
int RunCollector(const Config& config, const volatile std::sig_atomic_t& stop, ApiPtr api = {});
} // namespace collector
