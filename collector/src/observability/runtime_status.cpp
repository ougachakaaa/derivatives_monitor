#include "observability/runtime_status.hpp"

namespace collector {
namespace {
void Exec(sqlite3* db, const char* sql) {
    if (sqlite3_exec(db, sql, nullptr, nullptr, nullptr) != SQLITE_OK)
        throw std::runtime_error(sqlite3_errmsg(db));
}
struct Statement {
    sqlite3* db;
    sqlite3_stmt* stmt = nullptr;
    Statement(sqlite3* connection, const char* sql) : db(connection) {
        if (sqlite3_prepare_v2(db, sql, -1, &stmt, nullptr) != SQLITE_OK)
            throw std::runtime_error(sqlite3_errmsg(db));
    }
    ~Statement() { sqlite3_finalize(stmt); }
    void Check(int rc) { if (rc != SQLITE_OK) throw std::runtime_error(sqlite3_errmsg(db)); }
    void Number(int n, std::int64_t value) { Check(sqlite3_bind_int64(stmt, n, value)); }
    void Text(int n, const std::string& value) { Check(sqlite3_bind_text(stmt, n, value.c_str(), -1, SQLITE_TRANSIENT)); }
    void Null(int n) { Check(sqlite3_bind_null(stmt, n)); }
    void Time(int n, std::int64_t value) { if (value) Number(n, value); else Null(n); }
    void Run() {
        if (sqlite3_step(stmt) != SQLITE_DONE) throw std::runtime_error(sqlite3_errmsg(db));
    }
};
int Scalar(sqlite3* db, const char* sql) {
    Statement query(db, sql);
    if (sqlite3_step(query.stmt) != SQLITE_ROW) throw std::runtime_error(sqlite3_errmsg(db));
    return sqlite3_column_int(query.stmt, 0);
}
constexpr const char* kCurrentSchema =
    "CREATE TABLE current_status("
    "singleton INTEGER PRIMARY KEY CHECK(singleton=1),run_id TEXT NOT NULL,"
    "heartbeat_us INTEGER NOT NULL,updated_us INTEGER NOT NULL,"
    "process_state TEXT NOT NULL CHECK(process_state IN('starting','running','stopped','failed')),"
    "connected INTEGER NOT NULL CHECK(connected IN(0,1)),logged_in INTEGER NOT NULL CHECK(logged_in IN(0,1)),"
    "target_count INTEGER NOT NULL,subscribed_count INTEGER NOT NULL,subscription_failed INTEGER NOT NULL,"
    "trading_day TEXT,total_ticks_today INTEGER NOT NULL,ticks_received INTEGER NOT NULL,"
    "last_tick_received_us INTEGER,last_market_commit_us INTEGER,"
    "connections INTEGER NOT NULL,disconnections INTEGER NOT NULL,callbacks_accepted INTEGER NOT NULL,"
    "bars_written INTEGER NOT NULL,partial_bars INTEGER NOT NULL,late_callbacks INTEGER NOT NULL,"
    "invalid_trading_day INTEGER NOT NULL,invalid_event_time INTEGER NOT NULL,unknown_instrument INTEGER NOT NULL,"
    "event_time_regressions INTEGER NOT NULL)";
constexpr const char* kInstrumentSchema =
    "CREATE TABLE instrument_status("
    "instrument_id TEXT PRIMARY KEY,run_id TEXT NOT NULL,updated_us INTEGER NOT NULL,"
    "subscription TEXT NOT NULL CHECK(subscription IN('not_sent','pending','subscribed','failed')),"
    "error_id INTEGER NOT NULL,ticks_received INTEGER NOT NULL,last_tick_received_us INTEGER,"
    "callbacks_accepted INTEGER NOT NULL,bars_written INTEGER NOT NULL,partial_bars INTEGER NOT NULL,"
    "late_callbacks INTEGER NOT NULL,invalid_event_time INTEGER NOT NULL)";
void ValidateTable(sqlite3* db, const char* name, const char* expected) {
    Statement query(db, "SELECT sql FROM sqlite_master WHERE type='table' AND name=?");
    query.Text(1, name);
    if (sqlite3_step(query.stmt) != SQLITE_ROW)
        throw std::runtime_error("missing runtime status table");
    const auto* definition = sqlite3_column_text(query.stmt, 0);
    if (!definition || std::string(reinterpret_cast<const char*>(definition)) != expected)
        throw std::runtime_error("incompatible runtime status schema");
}
} // namespace

const char* ProcessStateName(ProcessState state) {
    switch (state) {
        case ProcessState::Starting: return "starting";
        case ProcessState::Running: return "running";
        case ProcessState::Stopped: return "stopped";
        case ProcessState::Failed: return "failed";
    }
    return "failed";
}

bool RuntimeStatusStore::Publish(const RuntimeSnapshot& snapshot, const DailyBarStore& market,
                                ProcessState state, std::int64_t heartbeat_us) {
    sqlite3* db = nullptr;
    try {
        if (std::filesystem::is_symlink(path_)) throw std::runtime_error("runtime database must not be a symlink");
        for (const auto* suffix : {"-journal", "-wal", "-shm"}) {
            if (std::filesystem::is_symlink(path_.string() + suffix))
                throw std::runtime_error("runtime sidecar must not be a symlink");
        }
        if (sqlite3_open_v2(path_.c_str(), &db, SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE, nullptr) != SQLITE_OK)
            throw std::runtime_error(db ? sqlite3_errmsg(db) : "cannot open runtime database");
        sqlite3_busy_timeout(db, 100);
        const auto version = Scalar(db, "PRAGMA user_version");
        const auto tables = Scalar(db, "SELECT count(*) FROM sqlite_master WHERE type='table'");
        if (version != 1 && !(version == 0 && tables == 0))
            throw std::runtime_error("unsupported runtime database version");
        if (version == 1) {
            ValidateTable(db, "current_status", kCurrentSchema);
            ValidateTable(db, "instrument_status", kInstrumentSchema);
            if (tables != 2) throw std::runtime_error("unexpected runtime tables");
        }
        Exec(db, "PRAGMA journal_mode=DELETE");
        Exec(db, "PRAGMA synchronous=FULL");
        Exec(db, "BEGIN IMMEDIATE");
        if (version == 0) {
            Exec(db, kCurrentSchema);
            Exec(db, kInstrumentSchema);
            Exec(db, "PRAGMA user_version=1");
        }
        const auto& session = snapshot.session;
        const auto& stats = snapshot.aggregation;
        std::int64_t subscribed = 0, failed = 0;
        const bool active = state == ProcessState::Starting || state == ProcessState::Running;
        for (const auto& item : session.instruments) {
            subscribed += active && session.logged_in && item.second.subscription == Subscription::Subscribed;
            failed += active && item.second.subscription == Subscription::Failed;
        }
        Exec(db, "DELETE FROM current_status");
        Exec(db, "DELETE FROM instrument_status");
        {
            Statement row(db, "INSERT INTO current_status VALUES(1,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)");
            row.Text(1, market.RunId()); row.Number(2, heartbeat_us); row.Number(3, heartbeat_us);
            row.Text(4, ProcessStateName(state)); row.Number(5, active && session.connected);
            row.Number(6, active && session.logged_in); row.Number(7, session.instruments.size());
            row.Number(8, subscribed); row.Number(9, failed);
            if (stats.ticks_by_day.empty()) { row.Null(10); row.Number(11, 0); }
            else { row.Text(10, stats.ticks_by_day.rbegin()->first); row.Number(11, stats.ticks_by_day.rbegin()->second); }
            row.Number(12, stats.ticks_received); row.Time(13, stats.last_tick_received_us);
            row.Time(14, market.LastCommitUs()); row.Number(15, session.connections); row.Number(16, session.disconnections);
            row.Number(17, stats.callbacks_accepted); row.Number(18, market.BarsWritten()); row.Number(19, market.PartialBars());
            row.Number(20, stats.late_callbacks); row.Number(21, stats.invalid_trading_day);
            row.Number(22, stats.invalid_event_time); row.Number(23, stats.unknown_instrument);
            row.Number(24, stats.event_time_regressions); row.Run();
        }
        for (const auto& item : session.instruments) {
            const auto ai = stats.instruments.find(item.first);
            const auto si = market.InstrumentStats().find(item.first);
            const auto a = ai == stats.instruments.end() ? InstrumentAggregationStats{} : ai->second;
            const auto s = si == market.InstrumentStats().end() ? InstrumentStoreStats{} : si->second;
            Statement row(db, "INSERT INTO instrument_status VALUES(?,?,?,?,?,?,?,?,?,?,?,?)");
            row.Text(1, item.first); row.Text(2, market.RunId()); row.Number(3, heartbeat_us);
            row.Text(4, active ? SubscriptionName(item.second.subscription) : "not_sent");
            row.Number(5, active ? item.second.error_id : 0); row.Number(6, a.ticks_received);
            row.Time(7, a.last_tick_received_us); row.Number(8, a.callbacks_accepted);
            row.Number(9, s.bars_written); row.Number(10, s.partial_bars); row.Number(11, a.late_callbacks);
            row.Number(12, a.invalid_event_time); row.Run();
        }
        Exec(db, "COMMIT");
        sqlite3_close(db);
        return true;
    } catch (const std::exception& error) {
        if (db) { sqlite3_exec(db, "ROLLBACK", nullptr, nullptr, nullptr); sqlite3_close(db); }
        ctp::Log("event=status_write_failed run_id=", market.RunId(), " message=\"", error.what(), "\"");
        return false;
    }
}
} // namespace collector
