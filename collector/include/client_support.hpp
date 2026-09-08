#pragma once
#include "ThostFtdcMdApi.h"
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <mutex>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace ctp {
namespace fs = std::filesystem;
inline std::mutex g_log_mutex;

template <typename... Args>
void Log(Args&&... args) {
    std::lock_guard<std::mutex> lock(g_log_mutex);
    (std::cout << ... << std::forward<Args>(args)) << std::endl;
}

inline std::string Trim(std::string value) {
    constexpr const char* whitespace = " \t\r\n";
    const auto begin = value.find_first_not_of(whitespace);
    if (begin == std::string::npos) {
        return {};
    }
    const auto end = value.find_last_not_of(whitespace);
    return value.substr(begin, end - begin + 1);
}

inline std::vector<std::string> SplitInstruments(const std::string& value) {
    std::vector<std::string> result;
    std::string current;
    for (const char ch : value) {
        if (ch == ':' || ch == ',') {
            current = Trim(current);
            if (!current.empty()) {
                result.push_back(current);
            }
            current.clear();
        } else {
            current.push_back(ch);
        }
    }
    current = Trim(current);
    if (!current.empty()) {
        result.push_back(current);
    }
    return result;
}

inline int ParseNonNegativeInt(const std::string& value, const std::string& key) {
    std::size_t parsed = 0;
    const int result = std::stoi(value, &parsed);
    if (parsed != value.size() || result < 0) {
        throw std::runtime_error(key + " must be a non-negative integer");
    }
    return result;
}

struct Config {
    std::string front;
    std::string broker_id;
    std::string user_id;
    std::string password;
    std::string user_product_info;
    std::vector<std::string> instruments;
    fs::path flow_path;
    fs::path csv_output_path;
    int connect_timeout_seconds = 20;
    int run_seconds = 0;
};

inline std::map<std::string, std::string> ReadConfigValues(const fs::path& requested_path) {
    const fs::path config_path = fs::absolute(requested_path);
    std::ifstream input(config_path);
    if (!input) {
        throw std::runtime_error("cannot open config file: " + config_path.string());
    }

    std::map<std::string, std::string> values;
    std::string section;
    std::string line;
    while (std::getline(input, line)) {
        line = Trim(line);
        if (line.empty() || line.front() == '#' || line.front() == ';') {
            continue;
        }
        if (line.front() == '[' && line.back() == ']') {
            section = Trim(line.substr(1, line.size() - 2));
            continue;
        }
        if (section != "config") {
            continue;
        }
        const auto separator = line.find('=');
        if (separator == std::string::npos) {
            throw std::runtime_error("invalid config line: " + line);
        }
        values[Trim(line.substr(0, separator))] = Trim(line.substr(separator + 1));
    }

    return values;
}

inline Config LoadConfig(const fs::path& requested_path) {
    const fs::path config_path = fs::absolute(requested_path);
    auto values = ReadConfigValues(config_path);
    Config config;
    config.front = values["FrontMdAddr"];
    config.broker_id = values["BrokerID"];
    config.user_id = values["UserID"];
    config.password = values["Password"];
    config.user_product_info = values["UserProductInfo"];
    config.instruments = SplitInstruments(values["Instruments"]);

    const std::string flow_value = values["FlowPath"].empty() ? "flow" : values["FlowPath"];
    config.flow_path = fs::path(flow_value);
    if (config.flow_path.is_relative()) {
        config.flow_path = config_path.parent_path() / config.flow_path;
    }

    if (!values["CsvOutputPath"].empty()) {
        config.csv_output_path = fs::path(values["CsvOutputPath"]);
        if (config.csv_output_path.is_relative()) {
            config.csv_output_path = config_path.parent_path() / config.csv_output_path;
        }
    }

    if (!values["ConnectTimeoutSeconds"].empty()) {
        config.connect_timeout_seconds =
            ParseNonNegativeInt(values["ConnectTimeoutSeconds"], "ConnectTimeoutSeconds");
    }
    if (config.connect_timeout_seconds == 0) {
        throw std::runtime_error("ConnectTimeoutSeconds must be greater than zero");
    }
    if (!values["RunSeconds"].empty()) {
        config.run_seconds = ParseNonNegativeInt(values["RunSeconds"], "RunSeconds");
    }
    if (config.front.empty()) {
        throw std::runtime_error("FrontMdAddr is required in [config]");
    }
    return config;
}

template <std::size_t N>
void ValidateField(const std::string& value, const char* name, const char (&)[N]) {
    if (value.size() >= N) {
        throw std::runtime_error(std::string(name) + " is too long for the CTP field");
    }
}

inline void ValidateConfig(const Config& config) {
    CThostFtdcReqUserLoginField request{};
    ValidateField(config.broker_id, "BrokerID", request.BrokerID);
    ValidateField(config.user_id, "UserID", request.UserID);
    ValidateField(config.password, "Password", request.Password);
    ValidateField(config.user_product_info, "UserProductInfo", request.UserProductInfo);
    CThostFtdcSpecificInstrumentField instrument{};
    for (const auto& value : config.instruments) {
        ValidateField(value, "InstrumentID", instrument.InstrumentID);
    }
}

template <std::size_t N>
void CopyField(char (&destination)[N], const std::string& source) {
    std::memset(destination, 0, N);
    std::memcpy(destination, source.data(), source.size());
}

template <std::size_t N>
std::string FieldString(const char (&value)[N]) {
    std::size_t length = 0;
    while (length < N && value[length] != '\0') {
        ++length;
    }
    return std::string(value, length);
}

inline std::string ErrorMessage(const CThostFtdcRspInfoField* info) {
    return info == nullptr ? std::string{} : FieldString(info->ErrorMsg);
}


} // namespace ctp
