#include "sqlite_test.hpp"
#include <chrono>
#include <csignal>
#include <fcntl.h>
#include <fstream>
#include <sys/wait.h>
#include <thread>

struct Child {
    pid_t pid = -1;
    Child(const char* exe, const char* preload, const std::filesystem::path& config, const std::filesystem::path& log, const char* seconds = "0") {
        pid = fork(); CHECK(pid >= 0);
        if (pid == 0) {
            const int out = open(log.c_str(), O_CREAT | O_WRONLY | O_APPEND, 0600);
            if (out < 0) _exit(126);
            dup2(out, STDOUT_FILENO); dup2(out, STDERR_FILENO); close(out);
            setenv("LD_PRELOAD", preload, 1);
            execl(exe, exe, "--config", config.c_str(), "--run-seconds", seconds, static_cast<char*>(nullptr));
            _exit(127);
        }
    }
    ~Child() { if (pid > 0) { kill(pid, SIGKILL); waitpid(pid, nullptr, 0); } }
    int Wait() {
        for (int i = 0; i < 200; ++i) {
            int status = 0;
            const int result = waitpid(pid, &status, WNOHANG);
            CHECK(result >= 0);
            if (result == pid) { pid = -1; return WIFEXITED(status) ? WEXITSTATUS(status) : 128 + WTERMSIG(status); }
            std::this_thread::sleep_for(std::chrono::milliseconds(20));
        }
        throw std::runtime_error("collector child did not exit promptly");
    }
};
template<class F> void Eventually(F&& predicate) {
    for (int i = 0; i < 200; ++i) {
        try { if (predicate()) return; } catch (const std::exception&) {}
        std::this_thread::sleep_for(std::chrono::milliseconds(20));
    }
    throw std::runtime_error("collector did not produce expected data");
}
int main(int argc, char** argv) {
    CHECK(argc == 3);
    TempDirectory temp;
    const auto config = temp.path / "config.ini", log = temp.path / "process.log";
    { std::ofstream out(config); out << "[config]\nFrontMdAddr=test-double\nInstruments=IF2609\nDataDirectory=data\nFlowPath=flow\nSnapshotIntervalMs=100\nStatusIntervalSeconds=1\nConnectTimeoutSeconds=2\n"; }
    const auto day1 = temp.path / "data/20260904.sqlite", day2 = temp.path / "data/20260907.sqlite";
    Child child(argv[1], argv[2], config, log);
    Eventually([&] { return std::filesystem::exists(day1) && TestDb(day1).Scalar("SELECT count(*)>=3 FROM snapshots") == "1"; });
    {
        Child duplicate(argv[1], argv[2], config, log);
        CHECK(duplicate.Wait() == 1);
    }
    Eventually([&] { return std::filesystem::exists(day2) && TestDb(day2).Scalar("SELECT count(*)>=2 FROM snapshots") == "1"; });
    {
        TestDb reader(day2);
        const auto before = std::stoi(reader.Scalar("SELECT count(*) FROM snapshots"));
        Eventually([&] { return std::stoi(reader.Scalar("SELECT count(*) FROM snapshots")) > before; });
        CHECK(sqlite3_exec(reader.db, "DELETE FROM snapshots", nullptr, nullptr, nullptr) == SQLITE_READONLY);
    }
    CHECK(kill(child.pid, SIGTERM) == 0); CHECK(child.Wait() == 0);
    int count_before = 0;
    {
        TestDb db(day1);
        count_before = std::stoi(db.Scalar("SELECT count(*) FROM snapshots"));
        CHECK(db.Scalar("PRAGMA integrity_check") == "ok");
        CHECK(db.Scalar("SELECT source LIKE '%TEST DOUBLE%' FROM runs LIMIT 1") == "1");
        CHECK(db.Scalar("SELECT stopped_us IS NOT NULL FROM runs") == "1");
    }
    // Restart the real CLI into the same datasets, then use its timed exit.
    Child restarted(argv[1], argv[2], config, log, "2"); CHECK(restarted.Wait() == 0);
    {
        TestDb db(day1);
        CHECK(std::stoi(db.Scalar("SELECT count(*) FROM snapshots")) > count_before);
        CHECK(db.Scalar("SELECT count(*) FROM runs") == "2");
        CHECK(db.Scalar("SELECT count(*) FROM runs WHERE stopped_us IS NULL") == "0");
        CHECK(db.Scalar("SELECT count(*) FROM snapshots WHERE TradingDay!='20260904'") == "0");
    }
    // SIGKILL is not a clean stop: prior WAL commits still survive and restart can append.
    Child killed(argv[1], argv[2], config, log);
    Eventually([&] { return TestDb(day1).Scalar("SELECT count(*) FROM runs") == "3"; });
    CHECK(kill(killed.pid, SIGKILL) == 0); CHECK(killed.Wait() == 128 + SIGKILL);
    Child recovered(argv[1], argv[2], config, log, "1"); CHECK(recovered.Wait() == 0);
    {
        TestDb db(day1);
        CHECK(db.Scalar("PRAGMA integrity_check") == "ok");
        CHECK(db.Scalar("SELECT count(*) FROM runs") == "4");
        CHECK(db.Scalar("SELECT count(*) FROM runs WHERE stopped_us IS NULL") == "1");
    }
    std::ifstream input(log); const std::string text((std::istreambuf_iterator<char>(input)), {});
    CHECK(text.find("TEST DOUBLE - synthetic market data") != std::string::npos);
    CHECK(text.find("event=front_disconnected") != std::string::npos);
    CHECK(text.find("connections=2") != std::string::npos);
    CHECK(text.find("event=snapshot_commit") != std::string::npos);
}
