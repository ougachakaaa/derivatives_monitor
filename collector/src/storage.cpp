#include "storage.hpp"
#include <fcntl.h>
#include <sys/file.h>
#include <unistd.h>
#include <iomanip>
#include <random>
#include <sstream>
#include <type_traits>

namespace collector {
namespace {
void Check(sqlite3* db, int rc) {
    if (rc != SQLITE_OK) throw std::runtime_error("SQLite: " + std::string(sqlite3_errmsg(db)));
}
void Exec(sqlite3* db, const std::string& sql) { Check(db, sqlite3_exec(db, sql.c_str(), nullptr, nullptr, nullptr)); }
class Statement {
public:
    Statement(sqlite3* db, const std::string& sql) : db_(db) {
        Check(db_, sqlite3_prepare_v2(db_, sql.c_str(), -1, &stmt_, nullptr));
    }
    ~Statement() { sqlite3_finalize(stmt_); }
    void Bind(int n, const std::string& value) { Check(db_, sqlite3_bind_text(stmt_, n, value.data(), static_cast<int>(value.size()), SQLITE_TRANSIENT)); }
    template<std::size_t N> void Bind(int n, const char (&value)[N]) { Bind(n, ctp::FieldString(value)); }
    void Bind(int n, std::int64_t value) { Check(db_, sqlite3_bind_int64(stmt_, n, value)); }
    void Bind(int n, int value) { Bind(n, static_cast<std::int64_t>(value)); }
    void Bind(int n, double value) {
        Check(db_, ValidNumber(value) ? sqlite3_bind_double(stmt_, n, value) : sqlite3_bind_null(stmt_, n));
    }
    void Run() {
        const int rc = sqlite3_step(stmt_);
        if (rc != SQLITE_DONE) Check(db_, rc);
        Check(db_, sqlite3_reset(stmt_));
        Check(db_, sqlite3_clear_bindings(stmt_));
    }
    std::string Scalar() {
        const int rc = sqlite3_step(stmt_);
        if (rc != SQLITE_ROW) { if (rc != SQLITE_DONE) Check(db_, rc); throw std::runtime_error("SQLite: missing metadata"); }
        const auto* value = sqlite3_column_text(stmt_, 0);
        return value ? reinterpret_cast<const char*>(value) : "";
    }
private:
    sqlite3* db_;
    sqlite3_stmt* stmt_ = nullptr;
};
std::string Scalar(sqlite3* db, const std::string& sql) { return Statement(db, sql).Scalar(); }
std::string NewRunId() {
    std::random_device random;
    std::ostringstream result;
    for (int i = 0; i < 4; ++i) result << std::hex << std::setw(8) << std::setfill('0') << random();
    return result.str();
}
} // namespace

DailyStore::DailyStore(std::filesystem::path directory, int interval_ms, const std::vector<std::string>& instruments, std::string source)
    : directory_(std::move(directory)), run_id_(NewRunId()), source_(std::move(source)), interval_ms_(interval_ms) {
    for (const auto& id : instruments) { if (!instruments_.empty()) instruments_ += ','; instruments_ += id; }
    std::filesystem::create_directories(directory_);
    lock_fd_ = ::open((directory_ / ".collector.lock").c_str(), O_CREAT | O_RDWR | O_CLOEXEC, 0600);
    if (lock_fd_ < 0) throw std::runtime_error("cannot open collector data-directory lock");
    if (flock(lock_fd_, LOCK_EX | LOCK_NB) != 0) {
        ::close(lock_fd_); lock_fd_ = -1;
        throw std::runtime_error("data directory already owned by another collector");
    }
}
DailyStore::~DailyStore() { Close(); if (lock_fd_ >= 0) ::close(lock_fd_); }

void DailyStore::Close() noexcept {
    if (db_) { sqlite3_close_v2(db_); db_ = nullptr; }
    day_.clear();
}

void DailyStore::Open(const std::string& day) {
    if (day_ == day) return;
    if (!ValidTradingDay(day)) throw std::runtime_error("invalid storage trading day");
    Close();
    try {
        const auto path = directory_ / (day + ".sqlite");
        const int open_result = sqlite3_open_v2(path.c_str(), &db_, SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE, nullptr);
        Check(db_, open_result);
        Check(db_, sqlite3_busy_timeout(db_, 1000));
        const auto version = Scalar(db_, "PRAGMA user_version");
        const bool empty = Scalar(db_, "SELECT count(*) FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'") == "0";
        if (version != "1" && !(version == "0" && empty)) throw std::runtime_error("unsupported SQLite schema version");
        if (!empty && (Scalar(db_, "PRAGMA application_id") != "1145914161" ||
                      Scalar(db_, "SELECT trading_day FROM dataset WHERE singleton=1") != day))
            throw std::runtime_error("SQLite dataset identity/trading day mismatch");
        if (Scalar(db_, "PRAGMA journal_mode=WAL") != "wal") throw std::runtime_error("SQLite WAL unavailable");
        Exec(db_, "PRAGMA synchronous=FULL");
        Exec(db_, "PRAGMA foreign_keys=ON");
        Exec(db_, "BEGIN IMMEDIATE");
        if (empty) {
            Exec(db_, "CREATE TABLE dataset(singleton INTEGER PRIMARY KEY CHECK(singleton=1), trading_day TEXT NOT NULL, schema_version INTEGER NOT NULL CHECK(schema_version=1));"
                      "INSERT INTO dataset VALUES(1,'" + day + "',1);"
                      "CREATE TABLE runs(run_id TEXT PRIMARY KEY, started_us INTEGER NOT NULL, stopped_us INTEGER, last_write_us INTEGER, snapshot_interval_ms INTEGER NOT NULL, instruments TEXT NOT NULL, source TEXT NOT NULL);"
                      "PRAGMA application_id=1145914161; PRAGMA user_version=1;");
            std::string schema = "CREATE TABLE snapshots(id INTEGER PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(run_id), sequence INTEGER NOT NULL, received_us INTEGER NOT NULL, snapshot_us INTEGER NOT NULL";
            VisitFacts(CThostFtdcDepthMarketDataField{}, [&](const char* name, const auto& value) {
                using T = std::decay_t<decltype(value)>;
                schema += std::string(",") + name + (std::is_floating_point_v<T> ? " REAL" : std::is_integral_v<T> ? " INTEGER" : " TEXT");
                if (std::string(name) == "TradingDay") schema += " NOT NULL CHECK(TradingDay='" + day + "')";
            });
            schema += ",UNIQUE(run_id,sequence)); CREATE INDEX snapshots_instrument_time ON snapshots(InstrumentID,received_us,id);";
            Exec(db_, schema);
        } else if (Scalar(db_, "SELECT schema_version FROM dataset WHERE singleton=1") != "1") {
            throw std::runtime_error("SQLite dataset schema mismatch");
        }
        Statement run(db_, "INSERT INTO runs(run_id,started_us,snapshot_interval_ms,instruments,source) VALUES(?,?,?,?,?) ON CONFLICT(run_id) DO NOTHING");
        run.Bind(1, run_id_); run.Bind(2, started_us_); run.Bind(3, interval_ms_); run.Bind(4, instruments_);
        run.Bind(5, source_); run.Run();
        Exec(db_, "COMMIT");
        day_ = day;
        touched_days_.insert(day);
        ctp::Log("event=sqlite_opened run_id=", run_id_, " trading_day=", day, " path=", path.string());
    } catch (...) {
        if (db_) sqlite3_exec(db_, "ROLLBACK", nullptr, nullptr, nullptr);
        Close(); throw;
    }
}

std::uint64_t DailyStore::Write(const std::vector<Snapshot>& snapshots) {
    std::map<std::string, std::vector<const Snapshot*>> groups;
    for (const auto& row : snapshots) {
        const auto day = ctp::FieldString(row.facts.TradingDay);
        if (!ValidTradingDay(day)) throw std::runtime_error("invalid snapshot trading day");
        groups[day].push_back(&row);
    }
    std::uint64_t total = 0;
    for (const auto& group : groups) {
        Open(group.first);
        std::string columns = "run_id,sequence,received_us,snapshot_us", placeholders = "?,?,?,?";
        VisitFacts(CThostFtdcDepthMarketDataField{}, [&](const char* name, const auto&) { columns += std::string(",") + name; placeholders += ",?"; });
        std::uint64_t inserted = 0;
        try {
            Statement insert(db_, "INSERT INTO snapshots(" + columns + ") VALUES(" + placeholders + ") ON CONFLICT(run_id,sequence) DO NOTHING");
            Exec(db_, "BEGIN IMMEDIATE");
            for (const auto* row : group.second) {
                insert.Bind(1, run_id_); insert.Bind(2, row->sequence); insert.Bind(3, row->received_us); insert.Bind(4, row->snapshot_us);
                int i = 5; VisitFacts(row->facts, [&](const char*, const auto& value) { insert.Bind(i++, value); });
                insert.Run(); inserted += sqlite3_changes(db_);
            }
            const auto committed_us = NowUs();
            Statement update(db_, "UPDATE runs SET last_write_us=? WHERE run_id=?");
            update.Bind(1, committed_us); update.Bind(2, run_id_); update.Run();
            Exec(db_, "COMMIT");
            written_ += inserted; total += inserted; last_commit_us_ = committed_us;
        } catch (...) { sqlite3_exec(db_, "ROLLBACK", nullptr, nullptr, nullptr); throw; }
    }
    return total;
}

void DailyStore::Finish() {
    for (const auto& day : touched_days_) {
        Open(day);
        Statement stop(db_, "UPDATE runs SET stopped_us=? WHERE run_id=?");
        stop.Bind(1, NowUs()); stop.Bind(2, run_id_); stop.Run();
    }
    Close();
}
} // namespace collector
