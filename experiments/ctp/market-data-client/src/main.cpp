#include "ThostFtdcMdApi.h"

#include <atomic>
#include <charconv>
#include <chrono>
#include <cmath>
#include <condition_variable>
#include <csignal>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <locale>
#include <map>
#include <mutex>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <utility>
#include <vector>

namespace fs = std::filesystem;

namespace {

volatile std::sig_atomic_t g_stop_requested = 0;
std::mutex g_log_mutex;

void HandleSignal(int) {
    g_stop_requested = 1;
}

template <typename... Args>
void Log(Args&&... args) {
    std::lock_guard<std::mutex> lock(g_log_mutex);
    (std::cout << ... << std::forward<Args>(args)) << std::endl;
}

std::string Trim(std::string value) {
    constexpr const char* whitespace = " \t\r\n";
    const auto begin = value.find_first_not_of(whitespace);
    if (begin == std::string::npos) {
        return {};
    }
    const auto end = value.find_last_not_of(whitespace);
    return value.substr(begin, end - begin + 1);
}

std::vector<std::string> SplitInstruments(const std::string& value) {
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

int ParseNonNegativeInt(const std::string& value, const std::string& key) {
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

Config LoadConfig(const fs::path& requested_path) {
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

void ValidateConfig(const Config& config) {
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

std::string ErrorMessage(const CThostFtdcRspInfoField* info) {
    return info == nullptr ? std::string{} : FieldString(info->ErrorMsg);
}

std::string Price(double value) {
    if (!std::isfinite(value) || std::abs(value) > 1.0e100) {
        return "null";
    }
    std::ostringstream stream;
    stream << std::fixed << std::setprecision(4) << value;
    return stream.str();
}

std::string CsvEscape(const std::string& value) {
    if (value.find_first_of(",\"\r\n") == std::string::npos) {
        return value;
    }

    std::string escaped;
    escaped.reserve(value.size() + 2);
    escaped.push_back('"');
    for (const char ch : value) {
        if (ch == '"') {
            escaped.push_back('"');
        }
        escaped.push_back(ch);
    }
    escaped.push_back('"');
    return escaped;
}

void AppendCsvCell(std::ostream& output, bool& first, const std::string& value) {
    if (!first) {
        output.put(',');
    }
    first = false;
    output << CsvEscape(value);
}

void AppendCsvCell(std::ostream& output, bool& first, double value) {
    if (!first) {
        output.put(',');
    }
    first = false;
    char buffer[128];
    const auto result = std::to_chars(
        buffer, buffer + sizeof(buffer), value, std::chars_format::general);
    if (result.ec == std::errc{}) {
        output.write(buffer, result.ptr - buffer);
    } else {
        output << std::setprecision(std::numeric_limits<double>::max_digits10) << value;
    }
}

void AppendCsvCell(std::ostream& output, bool& first, int value) {
    if (!first) {
        output.put(',');
    }
    first = false;
    output << value;
}

class MarketDataSpi final : public CThostFtdcMdSpi {
public:
    MarketDataSpi(CThostFtdcMdApi* api, Config config)
        : api_(api), config_(std::move(config)) {
        OpenCsvOutput();
    }

    void OnFrontConnected() override {
        Log("event=front_connected front=", config_.front);

        CThostFtdcReqUserLoginField request{};
        CopyField(request.BrokerID, config_.broker_id);
        CopyField(request.UserID, config_.user_id);
        CopyField(request.Password, config_.password);
        CopyField(request.UserProductInfo, config_.user_product_info);

        const int result = api_->ReqUserLogin(&request, ++request_id_);
        Log("event=login_request result=", result);
        if (result != 0) {
            CompleteLogin(false, result, "ReqUserLogin rejected locally");
        }
    }

    void OnFrontDisconnected(int reason) override {
        Log("event=front_disconnected reason=0x", std::hex, reason, std::dec);
    }

    void OnHeartBeatWarning(int time_lapse) override {
        Log("event=heartbeat_warning seconds=", time_lapse);
    }

    void OnRspUserLogin(CThostFtdcRspUserLoginField* response,
                        CThostFtdcRspInfoField* info,
                        int request_id,
                        bool is_last) override {
        const int error_id = info == nullptr ? 0 : info->ErrorID;
        const std::string error_message = ErrorMessage(info);
        const std::string trading_day =
            response == nullptr ? std::string{} : FieldString(response->TradingDay);
        Log("event=login_response request_id=", request_id,
            " is_last=", is_last,
            " error_id=", error_id,
            " error_message=\"", error_message, "\"",
            " trading_day=", trading_day);

        if (!is_last) {
            return;
        }
        if (error_id != 0) {
            CompleteLogin(false, error_id, error_message);
            return;
        }

        CompleteLogin(true, 0, error_message);
        SubscribeConfiguredInstruments();
    }

    void OnRspError(CThostFtdcRspInfoField* info,
                    int request_id,
                    bool is_last) override {
        Log("event=error_response request_id=", request_id,
            " is_last=", is_last,
            " error_id=", info == nullptr ? 0 : info->ErrorID,
            " error_message=\"", ErrorMessage(info), "\"");
    }

    void OnRspSubMarketData(CThostFtdcSpecificInstrumentField* instrument,
                            CThostFtdcRspInfoField* info,
                            int request_id,
                            bool is_last) override {
        Log("event=subscription_response instrument=",
            instrument == nullptr ? std::string{} : FieldString(instrument->InstrumentID),
            " request_id=", request_id,
            " is_last=", is_last,
            " error_id=", info == nullptr ? 0 : info->ErrorID,
            " error_message=\"", ErrorMessage(info), "\"");
    }

    void OnRtnDepthMarketData(CThostFtdcDepthMarketDataField* data) override {
        if (data == nullptr) {
            return;
        }
        Log("event=tick instrument=", FieldString(data->InstrumentID),
            " exchange=", FieldString(data->ExchangeID),
            " time=", FieldString(data->UpdateTime), '.',
            std::setfill('0'), std::setw(3), data->UpdateMillisec,
            std::setfill(' '),
            " last=", Price(data->LastPrice),
            " bid1=", Price(data->BidPrice1),
            " bid_volume1=", data->BidVolume1,
            " ask1=", Price(data->AskPrice1),
            " ask_volume1=", data->AskVolume1,
            " volume=", data->Volume,
            " open_interest=", Price(data->OpenInterest));
        WriteCsvRow(*data);
    }

    bool WaitForLogin(std::chrono::seconds timeout) {
        std::unique_lock<std::mutex> lock(state_mutex_);
        if (!state_changed_.wait_for(lock, timeout, [this] { return login_complete_; })) {
            login_error_id_ = -1;
            login_error_message_ = "timed out waiting for market-data login";
            return false;
        }
        return login_succeeded_;
    }

    int LoginErrorId() const {
        std::lock_guard<std::mutex> lock(state_mutex_);
        return login_error_id_;
    }

    std::string LoginErrorMessage() const {
        std::lock_guard<std::mutex> lock(state_mutex_);
        return login_error_message_;
    }

private:
    void OpenCsvOutput() {
        if (config_.csv_output_path.empty()) {
            return;
        }

        const fs::path parent = config_.csv_output_path.parent_path();
        if (!parent.empty()) {
            fs::create_directories(parent);
        }
        csv_output_.open(config_.csv_output_path, std::ios::out | std::ios::trunc);
        if (!csv_output_) {
            throw std::runtime_error(
                "cannot open CSV output: " + config_.csv_output_path.string());
        }
        csv_output_.imbue(std::locale::classic());
        csv_output_
            << "TradingDay,reserve1,ExchangeID,reserve2,LastPrice,"
               "PreSettlementPrice,PreClosePrice,PreOpenInterest,OpenPrice,"
               "HighestPrice,LowestPrice,Volume,Turnover,OpenInterest,ClosePrice,"
               "SettlementPrice,UpperLimitPrice,LowerLimitPrice,PreDelta,CurrDelta,"
               "UpdateTime,UpdateMillisec,BidPrice1,BidVolume1,AskPrice1,AskVolume1,"
               "BidPrice2,BidVolume2,AskPrice2,AskVolume2,BidPrice3,BidVolume3,"
               "AskPrice3,AskVolume3,BidPrice4,BidVolume4,AskPrice4,AskVolume4,"
               "BidPrice5,BidVolume5,AskPrice5,AskVolume5,AveragePrice,ActionDay,"
               "InstrumentID,ExchangeInstID,BandingUpperPrice,BandingLowerPrice\n";
        if (!csv_output_) {
            throw std::runtime_error(
                "cannot write CSV header: " + config_.csv_output_path.string());
        }
        Log("event=csv_opened path=", config_.csv_output_path.string());
    }

    void WriteCsvRow(const CThostFtdcDepthMarketDataField& data) {
        if (!csv_output_.is_open()) {
            return;
        }

        bool report_error = false;
        {
            std::lock_guard<std::mutex> lock(csv_mutex_);
            if (csv_write_failed_) {
                return;
            }
            bool first = true;
            AppendCsvCell(csv_output_, first, FieldString(data.TradingDay));
            AppendCsvCell(csv_output_, first, FieldString(data.reserve1));
            AppendCsvCell(csv_output_, first, FieldString(data.ExchangeID));
            AppendCsvCell(csv_output_, first, FieldString(data.reserve2));
            AppendCsvCell(csv_output_, first, data.LastPrice);
            AppendCsvCell(csv_output_, first, data.PreSettlementPrice);
            AppendCsvCell(csv_output_, first, data.PreClosePrice);
            AppendCsvCell(csv_output_, first, data.PreOpenInterest);
            AppendCsvCell(csv_output_, first, data.OpenPrice);
            AppendCsvCell(csv_output_, first, data.HighestPrice);
            AppendCsvCell(csv_output_, first, data.LowestPrice);
            AppendCsvCell(csv_output_, first, data.Volume);
            AppendCsvCell(csv_output_, first, data.Turnover);
            AppendCsvCell(csv_output_, first, data.OpenInterest);
            AppendCsvCell(csv_output_, first, data.ClosePrice);
            AppendCsvCell(csv_output_, first, data.SettlementPrice);
            AppendCsvCell(csv_output_, first, data.UpperLimitPrice);
            AppendCsvCell(csv_output_, first, data.LowerLimitPrice);
            AppendCsvCell(csv_output_, first, data.PreDelta);
            AppendCsvCell(csv_output_, first, data.CurrDelta);
            AppendCsvCell(csv_output_, first, FieldString(data.UpdateTime));
            AppendCsvCell(csv_output_, first, data.UpdateMillisec);
            AppendCsvCell(csv_output_, first, data.BidPrice1);
            AppendCsvCell(csv_output_, first, data.BidVolume1);
            AppendCsvCell(csv_output_, first, data.AskPrice1);
            AppendCsvCell(csv_output_, first, data.AskVolume1);
            AppendCsvCell(csv_output_, first, data.BidPrice2);
            AppendCsvCell(csv_output_, first, data.BidVolume2);
            AppendCsvCell(csv_output_, first, data.AskPrice2);
            AppendCsvCell(csv_output_, first, data.AskVolume2);
            AppendCsvCell(csv_output_, first, data.BidPrice3);
            AppendCsvCell(csv_output_, first, data.BidVolume3);
            AppendCsvCell(csv_output_, first, data.AskPrice3);
            AppendCsvCell(csv_output_, first, data.AskVolume3);
            AppendCsvCell(csv_output_, first, data.BidPrice4);
            AppendCsvCell(csv_output_, first, data.BidVolume4);
            AppendCsvCell(csv_output_, first, data.AskPrice4);
            AppendCsvCell(csv_output_, first, data.AskVolume4);
            AppendCsvCell(csv_output_, first, data.BidPrice5);
            AppendCsvCell(csv_output_, first, data.BidVolume5);
            AppendCsvCell(csv_output_, first, data.AskPrice5);
            AppendCsvCell(csv_output_, first, data.AskVolume5);
            AppendCsvCell(csv_output_, first, data.AveragePrice);
            AppendCsvCell(csv_output_, first, FieldString(data.ActionDay));
            AppendCsvCell(csv_output_, first, FieldString(data.InstrumentID));
            AppendCsvCell(csv_output_, first, FieldString(data.ExchangeInstID));
            AppendCsvCell(csv_output_, first, data.BandingUpperPrice);
            AppendCsvCell(csv_output_, first, data.BandingLowerPrice);
            csv_output_.put('\n');
            if (!csv_output_) {
                csv_write_failed_ = true;
                report_error = true;
            }
        }
        if (report_error) {
            Log("event=csv_write_failed path=", config_.csv_output_path.string());
        }
    }

    void CompleteLogin(bool succeeded, int error_id, const std::string& message) {
        {
            std::lock_guard<std::mutex> lock(state_mutex_);
            login_succeeded_ = succeeded;
            login_complete_ = true;
            login_error_id_ = error_id;
            login_error_message_ = message;
        }
        state_changed_.notify_all();
    }

    void SubscribeConfiguredInstruments() {
        if (config_.instruments.empty()) {
            Log("event=ready instruments=0 message=\"login verified; no instruments configured\"");
            return;
        }

        std::vector<char*> instrument_ids;
        instrument_ids.reserve(config_.instruments.size());
        for (auto& instrument : config_.instruments) {
            instrument_ids.push_back(instrument.data());
        }
        const int result = api_->SubscribeMarketData(
            instrument_ids.data(), static_cast<int>(instrument_ids.size()));
        Log("event=subscription_request count=", instrument_ids.size(), " result=", result);
    }

    CThostFtdcMdApi* api_;
    Config config_;
    std::ofstream csv_output_;
    std::mutex csv_mutex_;
    bool csv_write_failed_ = false;
    std::atomic<int> request_id_{0};
    mutable std::mutex state_mutex_;
    std::condition_variable state_changed_;
    bool login_complete_ = false;
    bool login_succeeded_ = false;
    int login_error_id_ = 0;
    std::string login_error_message_;
};

struct CommandLine {
    fs::path config_path = "config.example.ini";
    std::vector<std::string> instruments;
    fs::path csv_output_path;
    int run_seconds = -1;
    bool show_help = false;
};

void PrintUsage(const char* executable) {
    std::cout
        << "Usage: " << executable << " [options]\n"
        << "  --config PATH          INI configuration file\n"
        << "  --instrument CODE      Subscribe one instrument; repeatable\n"
        << "  --csv PATH             Write raw CTP depth-market-data rows to CSV\n"
        << "  --run-seconds N        Exit N seconds after login; 0 waits for a signal\n"
        << "  --help                 Show this help\n";
}

CommandLine ParseCommandLine(int argc, char* argv[]) {
    CommandLine result;
    for (int index = 1; index < argc; ++index) {
        const std::string argument = argv[index];
        auto require_value = [&](const char* option) -> std::string {
            if (++index >= argc) {
                throw std::runtime_error(std::string(option) + " requires a value");
            }
            return argv[index];
        };

        if (argument == "--config") {
            result.config_path = require_value("--config");
        } else if (argument == "--instrument") {
            result.instruments.push_back(require_value("--instrument"));
        } else if (argument == "--csv") {
            result.csv_output_path = require_value("--csv");
        } else if (argument == "--run-seconds") {
            result.run_seconds = ParseNonNegativeInt(
                require_value("--run-seconds"), "--run-seconds");
        } else if (argument == "--help" || argument == "-h") {
            result.show_help = true;
        } else {
            throw std::runtime_error("unknown argument: " + argument);
        }
    }
    return result;
}

void WaitForRunWindow(int run_seconds) {
    const auto started = std::chrono::steady_clock::now();
    while (!g_stop_requested) {
        if (run_seconds > 0 &&
            std::chrono::steady_clock::now() - started >= std::chrono::seconds(run_seconds)) {
            break;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }
}

}  // namespace

int main(int argc, char* argv[]) {
    CThostFtdcMdApi* api = nullptr;
    try {
        CommandLine command_line = ParseCommandLine(argc, argv);
        if (command_line.show_help) {
            PrintUsage(argv[0]);
            return 0;
        }

        Config config = LoadConfig(command_line.config_path);
        if (!command_line.instruments.empty()) {
            config.instruments = std::move(command_line.instruments);
        }
        if (!command_line.csv_output_path.empty()) {
            config.csv_output_path = fs::absolute(command_line.csv_output_path);
        }
        if (command_line.run_seconds >= 0) {
            config.run_seconds = command_line.run_seconds;
        }
        ValidateConfig(config);

        fs::create_directories(config.flow_path);
        std::string flow_path = config.flow_path.string();
        if (flow_path.back() != '/') {
            flow_path.push_back('/');
        }

        std::signal(SIGINT, HandleSignal);
        std::signal(SIGTERM, HandleSignal);

        Log("event=start api_version=\"", CThostFtdcMdApi::GetApiVersion(),
            "\" front=", config.front,
            " flow_path=", flow_path,
            " csv_path=", config.csv_output_path.string(),
            " instruments=", config.instruments.size());

        api = CThostFtdcMdApi::CreateFtdcMdApi(flow_path.c_str(), false, false, true);
        if (api == nullptr) {
            throw std::runtime_error("CreateFtdcMdApi returned null");
        }

        MarketDataSpi spi(api, config);
        api->RegisterSpi(&spi);
        api->RegisterFront(config.front.data());
        api->Init();

        if (!spi.WaitForLogin(std::chrono::seconds(config.connect_timeout_seconds))) {
            Log("event=start_failed error_id=", spi.LoginErrorId(),
                " error_message=\"", spi.LoginErrorMessage(), "\"");
            api->RegisterSpi(nullptr);
            api->Release();
            api = nullptr;
            return 1;
        }

        WaitForRunWindow(config.run_seconds);
        Log("event=stop reason=", g_stop_requested ? "signal" : "run_window_complete");
        api->RegisterSpi(nullptr);
        api->Release();
        api = nullptr;
        return 0;
    } catch (const std::exception& error) {
        if (api != nullptr) {
            api->RegisterSpi(nullptr);
            api->Release();
        }
        std::cerr << "fatal: " << error.what() << std::endl;
        return 1;
    }
}
