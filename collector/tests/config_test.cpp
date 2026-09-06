#include "config.hpp"
#include "test.hpp"
int main(int argc, char** argv) {
    CHECK(argc == 2);
    auto config = collector::LoadConfig(argv[1]);
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
}
