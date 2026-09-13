#include "sqlite_test.hpp"

#include <chrono>
#include <csignal>
#include <fcntl.h>
#include <fstream>
#include <sys/wait.h>
#include <thread>

struct Child {
    pid_t pid = -1;
    Child(const char* exe, const char* preload, const std::filesystem::path& config,
          const std::filesystem::path& log, const char* seconds = "0") {
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
        for (int i = 0; i < 300; ++i) {
            int status = 0;
            const int result = waitpid(pid, &status, WNOHANG);
            CHECK(result >= 0);
            if (result == pid) {
                pid = -1;
                return WIFEXITED(status) ? WEXITSTATUS(status) : 128 + WTERMSIG(status);
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(20));
        }
        throw std::runtime_error("collector child did not exit promptly");
    }
};

template<class F> void Eventually(F&& predicate) {
    for (int i = 0; i < 300; ++i) {
        try { if (predicate()) return; } catch (const std::exception&) {}
        std::this_thread::sleep_for(std::chrono::milliseconds(20));
    }
    throw std::runtime_error("collector did not publish expected process state");
}

std::string Read(const std::filesystem::path& path) {
    std::ifstream input(path);
    return std::string(std::istreambuf_iterator<char>(input), {});
}

int main(int argc, char** argv) {
    CHECK(argc == 3);
    TempDirectory temp;
    const auto config = temp.path / "config.ini";
    const auto log = temp.path / "process.log";
    const auto health = temp.path / "data/.collector-status.json";
    {
        std::ofstream out(config);
        out << "# TEST DOUBLE: no real front\n[config]\nFrontMdAddr=test-double\nInstruments=IF2609\n"
               "DataDirectory=data\nFlowPath=flow\nStatusIntervalSeconds=1\nConnectTimeoutSeconds=2\n";
    }
    Child child(argv[1], argv[2], config, log);
    Eventually([&] { return Read(health).find("\"process_state\": \"running\"") != std::string::npos; });
    CHECK(Read(health).find("\"schema_version\": 2") != std::string::npos);
    {
        Child duplicate(argv[1], argv[2], config, log);
        CHECK(duplicate.Wait() == 1);
    }
    CHECK(kill(child.pid, SIGTERM) == 0);
    CHECK(child.Wait() == 0);
    CHECK(Read(health).find("\"process_state\": \"stopped\"") != std::string::npos);

    Child restarted(argv[1], argv[2], config, log, "1");
    CHECK(restarted.Wait() == 0);
    CHECK(Read(health).find("\"process_state\": \"stopped\"") != std::string::npos);
    std::ifstream input(log);
    const std::string text((std::istreambuf_iterator<char>(input)), {});
    CHECK(text.find("TEST DOUBLE - synthetic market data") != std::string::npos);
    CHECK(text.find("event=front_disconnected") != std::string::npos);
    CHECK(text.find("callbacks_accepted=") != std::string::npos);
    CHECK(text.find("event=snapshot_commit") == std::string::npos);
}
