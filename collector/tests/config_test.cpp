#include "config.hpp"
#include "test.hpp"
#include <unistd.h>
#include <fstream>
int main(int argc, char** argv) {
    CHECK(argc == 2);
    CHECK(collector::Config{}.snapshot_interval_ms == 15000);
    char pattern[] = "/tmp/dm-config-test-XXXXXX";
    const int fd = mkstemp(pattern); CHECK(fd >= 0); close(fd);
    struct Cleanup {
        std::filesystem::path path;
        ~Cleanup() { std::error_code error; std::filesystem::remove(path, error); }
    } cleanup{pattern};
    const auto& path = cleanup.path;
    const auto load_interval = [&](const std::string& line) {
        { std::ofstream out(path); out << "[config]\nFrontMdAddr=test-double\n" << line << "\n"; }
        return collector::LoadConfig(path).snapshot_interval_ms;
    };
    CHECK(load_interval("") == 15000);
    for (const int interval : {1, 50, 1000, 15000, 60000})
        CHECK(load_interval("SnapshotIntervalMs=" + std::to_string(interval)) == interval);
    for (const auto* value : {"0", "-1", "60001", "15oops"})
        Throws([&] { load_interval(std::string("SnapshotIntervalMs=") + value); });
    auto config = collector::LoadConfig(argv[1]);
    CHECK(config.snapshot_interval_ms == 15000);
    CHECK(config.data_directory.is_absolute());
    CHECK(config.flow_path.is_absolute());
    Throws([&] { collector::ValidateConfig(config); });
    config.instruments = {"IF2609", "IO2609-C-4000", "IF2609"};
    collector::ValidateConfig(config);
    CHECK(config.instruments.size() == 2);
    config.instruments = {std::string(100, 'X')};
    Throws([&] { collector::ValidateConfig(config); });
    config.instruments = {""};
    Throws([&] { collector::ValidateConfig(config); });
    Throws([] { ctp::ParseNonNegativeInt("1oops", "test"); });
    Throws([] { ctp::ParseNonNegativeInt("-1", "test"); });
    const auto directory = std::filesystem::temp_directory_path() / ("collector-config-" + std::to_string(getpid()));
    std::filesystem::create_directories(directory);
    const auto ini = directory / "config.ini", list = directory / "instruments.txt";
    { std::ofstream out(ini); out << "[config]\nFrontMdAddr=test\nInstruments=IC2609\nInstrumentsFile=instruments.txt\n"; }
    { std::ofstream out(list); out << "# CFFEX\nIF2609\r\n\nIO2609-C-4600\nIF2609\n"; }
    auto from_file = collector::LoadConfig(ini); collector::ValidateConfig(from_file);
    CHECK(from_file.instruments == (std::vector<std::string>{"IF2609", "IO2609-C-4600"}));
    { std::ofstream out(list); }
    auto empty = collector::LoadConfig(ini); Throws([&] { collector::ValidateConfig(empty); });
    std::filesystem::remove(list);
    Throws([&] { collector::LoadConfig(ini); });
    auto overridden = collector::LoadConfig(ini, false);
    overridden.instruments = {"TL2612"}; collector::ValidateConfig(overridden);
    for (int i = 0; i < 10001; ++i) overridden.instruments.push_back("IO2609-C-" + std::to_string(i));
    Throws([&] { collector::ValidateConfig(overridden); });
    std::filesystem::remove_all(directory);
}
