#include "app/runtime.hpp"

namespace {
volatile std::sig_atomic_t stop_requested = 0;
void HandleSignal(int) { stop_requested = 1; }
}

int main(int argc, char** argv) {
    try {
        std::filesystem::path path = "config.ini";
        std::vector<std::string> instruments;
        int run_seconds = -1;
        bool check = false;
        for (int i = 1; i < argc; ++i) {
            const std::string arg = argv[i];
            const auto value = [&]() -> std::string {
                if (++i == argc) throw std::runtime_error(arg + " requires a value");
                return argv[i];
            };
            if (arg == "--help" || arg == "-h") {
                std::cout << "Usage: data_collector --config PATH [--instrument CODE ...] [--run-seconds N] [--check-config]\n";
                return 0;
            }
            if (arg == "--config") path = value();
            else if (arg == "--instrument") instruments.push_back(value());
            else if (arg == "--run-seconds") run_seconds = ctp::ParseNonNegativeInt(value(), arg);
            else if (arg == "--check-config") check = true;
            else throw std::runtime_error("unknown argument: " + arg);
        }
        auto config = collector::LoadConfig(path, instruments.empty());
        if (!instruments.empty()) config.instruments = std::move(instruments);
        if (run_seconds >= 0) config.run_seconds = run_seconds;
        collector::ValidateConfig(config);
        if (check) {
            ctp::Log("event=config_valid instruments=", config.instruments.size(),
                     " data_directory=", config.data_directory.string());
            return 0;
        }
        std::signal(SIGINT, HandleSignal);
        std::signal(SIGTERM, HandleSignal);
        return collector::RunCollector(config, stop_requested);
    } catch (const std::exception& error) {
        std::cerr << "event=fatal message=\"" << error.what() << "\"\n";
        return 1;
    }
}
