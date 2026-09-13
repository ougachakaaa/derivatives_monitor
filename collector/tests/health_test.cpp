#include "observability/health.hpp"
#include "sqlite_test.hpp"

std::string Read(const std::filesystem::path& path) {
    std::ifstream input(path);
    return std::string(std::istreambuf_iterator<char>(input), {});
}

int main() {
    using namespace collector;
    TempDirectory temp;
    DailyBarStore store(temp.path, {"IF2609"}, "TEST DOUBLE - health");
    SessionStatus session;
    AggregationStats stats;
    session.instruments.emplace("IF2609", InstrumentStatus{});
    stats.instruments.emplace("IF2609", InstrumentAggregationStats{});
    const auto path = temp.path / ".collector-status.json";
    CHECK(PublishHealth(temp.path, session, stats, store, ProcessState::Starting));
    CHECK(Read(path).find("\"schema_version\": 2") != std::string::npos);
    CHECK(Read(path).find("\"process_state\": \"starting\"") != std::string::npos);
    session.connected = session.logged_in = true;
    session.instruments.at("IF2609").subscription = Subscription::Subscribed;
    stats.callbacks_accepted = 3;
    stats.instruments.at("IF2609").callbacks_accepted = 3;
    CHECK(PublishHealth(temp.path, session, stats, store, ProcessState::Running));
    CHECK(Read(path).find("\"callbacks_accepted\": 3") != std::string::npos);
    CHECK(Read(path).find("\"bars_written\": 0") != std::string::npos);
    CHECK(Read(path).find("\"connected\": true") != std::string::npos);
    const auto coverage = temp.path / ".collector-coverage.json";
    CHECK(Read(coverage).find("\"schema_version\":2") != std::string::npos);
    CHECK(Read(coverage).find("\"id\":\"IF2609\"") != std::string::npos);
    CHECK(Read(coverage).find("\"callbacks_accepted\":3") != std::string::npos);
    CHECK(Read(coverage).find("\"partial_bars\":0") != std::string::npos);
    CHECK(PublishHealth(temp.path, session, stats, store, ProcessState::Stopped));
    CHECK(Read(path).find("\"connected\": false") != std::string::npos);
    CHECK(PublishHealth(temp.path, session, stats, store, ProcessState::Failed));
    CHECK(Read(path).find("\"process_state\": \"failed\"") != std::string::npos);
    std::filesystem::remove(path);
    std::filesystem::create_directory(path);
    CHECK(!PublishHealth(temp.path, session, stats, store, ProcessState::Running));
    CHECK(!std::filesystem::exists(temp.path / ".collector-status.tmp"));
}
