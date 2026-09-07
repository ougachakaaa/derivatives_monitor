#pragma once
#include "client_support.hpp"
#include <algorithm>
#include <cctype>

namespace collector {
struct Config : ctp::Config {
    std::filesystem::path data_directory;
    int snapshot_interval_ms = 1000;
    int status_interval_seconds = 10;
    int retry_interval_seconds = 5;
    int subscription_batch_size = 100;
};

inline Config LoadConfig(const std::filesystem::path& path, bool read_instruments_file = true) {
    Config config;
    static_cast<ctp::Config&>(config) = ctp::LoadConfig(path);
    auto values = ctp::ReadConfigValues(path);
    if (read_instruments_file && !values["InstrumentsFile"].empty()) {
        std::filesystem::path file = values["InstrumentsFile"];
        if (file.is_relative()) file = std::filesystem::absolute(path).parent_path() / file;
        std::ifstream input(file);
        if (!input) throw std::runtime_error("cannot open InstrumentsFile: " + file.string());
        config.instruments.clear();
        std::string line;
        while (std::getline(input, line)) {
            line = ctp::Trim(line);
            if (!line.empty() && line.front() != '#' && line.front() != ';') config.instruments.push_back(line);
        }
        if (input.bad()) throw std::runtime_error("cannot read InstrumentsFile");
    }
    config.data_directory = values["DataDirectory"].empty() ? "data" : values["DataDirectory"];
    if (config.data_directory.is_relative())
        config.data_directory = std::filesystem::absolute(path).parent_path() / config.data_directory;
    const auto positive = [&](const char* key, int& target, int maximum) {
        if (!values[key].empty()) target = ctp::ParseNonNegativeInt(values[key], key);
        if (target <= 0 || target > maximum)
            throw std::runtime_error(std::string(key) + " out of range");
    };
    positive("SnapshotIntervalMs", config.snapshot_interval_ms, 60000);
    positive("StatusIntervalSeconds", config.status_interval_seconds, 3600);
    positive("RetryIntervalSeconds", config.retry_interval_seconds, 300);
    positive("SubscriptionBatchSize", config.subscription_batch_size, 100);
    if (!config.csv_output_path.empty()) throw std::runtime_error("Collector does not accept CsvOutputPath");
    return config;
}

inline void ValidateConfig(Config& config) {
    ctp::ValidateConfig(config);
    if (config.connect_timeout_seconds <= 0 || config.connect_timeout_seconds > 3600)
        throw std::runtime_error("ConnectTimeoutSeconds must be in 1..3600");
    if (config.instruments.empty()) throw std::runtime_error("Instruments must not be empty");
    for (const auto& id : config.instruments) {
        if (id.empty() || !std::all_of(id.begin(), id.end(), [](unsigned char c) {
                return std::isalnum(c) || c == '-' || c == '_';
            })) throw std::runtime_error("invalid InstrumentID");
    }
    std::sort(config.instruments.begin(), config.instruments.end());
    config.instruments.erase(std::unique(config.instruments.begin(), config.instruments.end()), config.instruments.end());
    if (config.instruments.size() > 10000) throw std::runtime_error("at most 10000 instruments supported");
}
} // namespace collector
