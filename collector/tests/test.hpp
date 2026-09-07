#pragma once
#include <stdexcept>
#include <string>
#define CHECK(condition) do { if (!(condition)) throw std::runtime_error(std::string("check failed: ") + #condition); } while (false)
template<class F> void Throws(F&& f) {
    bool threw = false;
    try { f(); } catch (const std::exception&) { threw = true; }
    CHECK(threw);
}
