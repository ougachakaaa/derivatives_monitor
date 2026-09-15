#include "observability/runtime_status.hpp"

#include <sstream>

namespace collector {
namespace {
void Exec(sqlite3* db, const std::string& sql) {
    char* message = nullptr;
    if (sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &message) != SQLITE_OK) {
        const std::string detail = message ? message : sqlite3_errmsg(db);
        sqlite3_free(message);
        throw std::runtime_error(detail);
    }
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
    void Run() { if (sqlite3_step(stmt) != SQLITE_DONE) throw std::runtime_error(sqlite3_errmsg(db)); }
};

std::string Scalar(sqlite3* db, const std::string& sql) {
    Statement query(db, sql.c_str());
    if (sqlite3_step(query.stmt) != SQLITE_ROW) throw std::runtime_error(sqlite3_errmsg(db));
    const auto* value = sqlite3_column_text(query.stmt, 0);
    return value ? reinterpret_cast<const char*>(value) : "";
}

constexpr const char* kRunsSchema =
    "CREATE TABLE runs("
    "run_id TEXT PRIMARY KEY NOT NULL CHECK(length(run_id)=32 AND run_id NOT GLOB '*[^0-9a-f]*'),"
    "started_us INTEGER NOT NULL CHECK(started_us>0),ended_us INTEGER,"
    "terminal_state TEXT CHECK(terminal_state IN('stopped','failed')),"
    "instruments TEXT NOT NULL,source TEXT NOT NULL,"
    "CHECK((ended_us IS NULL AND terminal_state IS NULL) OR "
    "(ended_us IS NOT NULL AND ended_us>=started_us AND terminal_state IS NOT NULL)))";
constexpr const char* kCurrentSchema =
    "CREATE TABLE current_status("
    "singleton INTEGER PRIMARY KEY CHECK(singleton=1),"
    "run_id TEXT NOT NULL REFERENCES runs(run_id),"
    "heartbeat_us INTEGER NOT NULL CHECK(heartbeat_us>0),"
    "updated_us INTEGER NOT NULL CHECK(updated_us=heartbeat_us),"
    "process_state TEXT NOT NULL CHECK(process_state IN('starting','running','stopped','failed')),"
    "connected INTEGER NOT NULL CHECK(connected IN(0,1)),"
    "logged_in INTEGER NOT NULL CHECK(logged_in IN(0,1) AND logged_in<=connected),"
    "target_count INTEGER NOT NULL CHECK(target_count>=0),"
    "subscribed_count INTEGER NOT NULL CHECK(subscribed_count>=0 AND subscribed_count<=target_count),"
    "subscription_failed INTEGER NOT NULL CHECK(subscription_failed>=0 AND subscription_failed<=target_count),"
    "trading_day TEXT CHECK(length(trading_day)=8 AND trading_day NOT GLOB '*[^0-9]*'),"
    "total_ticks_today INTEGER NOT NULL CHECK(total_ticks_today>=0),"
    "ticks_received INTEGER NOT NULL CHECK(ticks_received>=0),"
    "last_tick_received_us INTEGER CHECK(last_tick_received_us>0),"
    "last_market_commit_us INTEGER CHECK(last_market_commit_us>0),"
    "connections INTEGER NOT NULL CHECK(connections>=0),disconnections INTEGER NOT NULL CHECK(disconnections>=0),"
    "callbacks_accepted INTEGER NOT NULL CHECK(callbacks_accepted>=0),"
    "bars_written INTEGER NOT NULL CHECK(bars_written>=0),"
    "partial_bars INTEGER NOT NULL CHECK(partial_bars>=0 AND partial_bars<=bars_written),"
    "late_callbacks INTEGER NOT NULL CHECK(late_callbacks>=0),"
    "invalid_trading_day INTEGER NOT NULL CHECK(invalid_trading_day>=0),"
    "invalid_event_time INTEGER NOT NULL CHECK(invalid_event_time>=0),"
    "unknown_instrument INTEGER NOT NULL CHECK(unknown_instrument>=0),"
    "event_time_regressions INTEGER NOT NULL CHECK(event_time_regressions>=0),"
    "CHECK(ticks_received=callbacks_accepted+late_callbacks))";
constexpr const char* kInstrumentSchema =
    "CREATE TABLE instrument_status("
    "instrument_id TEXT PRIMARY KEY NOT NULL,run_id TEXT NOT NULL REFERENCES runs(run_id),"
    "updated_us INTEGER NOT NULL CHECK(updated_us>0),"
    "subscription TEXT NOT NULL CHECK(subscription IN('not_sent','pending','subscribed','failed')),"
    "error_id INTEGER NOT NULL,ticks_received INTEGER NOT NULL CHECK(ticks_received>=0),"
    "last_tick_received_us INTEGER CHECK(last_tick_received_us>0),"
    "callbacks_accepted INTEGER NOT NULL CHECK(callbacks_accepted>=0),"
    "bars_written INTEGER NOT NULL CHECK(bars_written>=0),"
    "partial_bars INTEGER NOT NULL CHECK(partial_bars>=0 AND partial_bars<=bars_written),"
    "late_callbacks INTEGER NOT NULL CHECK(late_callbacks>=0),"
    "invalid_event_time INTEGER NOT NULL CHECK(invalid_event_time>=0),"
    "CHECK(ticks_received=callbacks_accepted+late_callbacks))";
constexpr const char* kHistorySchema =
    "CREATE TABLE runtime_snapshots("
    "run_id TEXT NOT NULL REFERENCES runs(run_id),"
    "interval_start_us INTEGER NOT NULL CHECK(interval_start_us%15000000=0),"
    "interval_end_us INTEGER NOT NULL CHECK(interval_end_us=interval_start_us+15000000),"
    "observed_us INTEGER NOT NULL CHECK(observed_us>=interval_end_us),"
    "process_state TEXT NOT NULL CHECK(process_state IN('starting','running')),"
    "connected INTEGER NOT NULL CHECK(connected IN(0,1)),"
    "logged_in INTEGER NOT NULL CHECK(logged_in IN(0,1) AND logged_in<=connected),"
    "target_count INTEGER NOT NULL CHECK(target_count>=0),"
    "subscribed_count INTEGER NOT NULL CHECK(subscribed_count>=0 AND subscribed_count<=target_count),"
    "subscription_failed INTEGER NOT NULL CHECK(subscription_failed>=0 AND subscription_failed<=target_count),"
    "tick_count INTEGER NOT NULL CHECK(tick_count>=0),"
    "market_bar_count INTEGER NOT NULL CHECK(market_bar_count>=0),"
    "partial_bar_count INTEGER NOT NULL CHECK(partial_bar_count>=0 AND partial_bar_count<=market_bar_count),"
    "last_tick_received_us INTEGER CHECK(last_tick_received_us>0),"
    "last_market_commit_us INTEGER CHECK(last_market_commit_us>0),"
    "PRIMARY KEY(run_id,interval_start_us))";
constexpr const char* kHistoryIndexSchema =
    "CREATE INDEX runtime_snapshots_interval ON runtime_snapshots(interval_start_us)";

void CheckPaths(const std::filesystem::path& path) {
    if (std::filesystem::is_symlink(path)) throw std::runtime_error("runtime database must not be a symlink");
    for (const auto* suffix : {"-journal", "-wal", "-shm"})
        if (std::filesystem::is_symlink(path.string() + suffix))
            throw std::runtime_error("runtime sidecar must not be a symlink");
}

sqlite3* Open(const std::filesystem::path& path) {
    CheckPaths(path);
    sqlite3* db = nullptr;
    if (sqlite3_open_v2(path.c_str(), &db, SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE, nullptr) != SQLITE_OK) {
        const std::string detail = db ? sqlite3_errmsg(db) : "cannot open runtime database";
        if (db) sqlite3_close(db);
        throw std::runtime_error(detail);
    }
    try {
        if (sqlite3_busy_timeout(db, 100) != SQLITE_OK) throw std::runtime_error(sqlite3_errmsg(db));
        Exec(db, "PRAGMA journal_mode=DELETE");
        Exec(db, "PRAGMA synchronous=FULL");
        Exec(db, "PRAGMA foreign_keys=ON");
        return db;
    } catch (...) { sqlite3_close(db); throw; }
}

void ValidateSchema(sqlite3* db) {
    if (Scalar(db, "SELECT count(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'") != "4" ||
        Scalar(db, "SELECT sql FROM sqlite_master WHERE type='table' AND name='runs'") != kRunsSchema ||
        Scalar(db, "SELECT sql FROM sqlite_master WHERE type='table' AND name='current_status'") != kCurrentSchema ||
        Scalar(db, "SELECT sql FROM sqlite_master WHERE type='table' AND name='instrument_status'") != kInstrumentSchema ||
        Scalar(db, "SELECT sql FROM sqlite_master WHERE type='table' AND name='runtime_snapshots'") != kHistorySchema ||
        Scalar(db, "SELECT sql FROM sqlite_master WHERE type='index' AND name='runtime_snapshots_interval'") != kHistoryIndexSchema)
        throw std::runtime_error("incompatible runtime database schema");
}

std::string JsonInstruments(const std::string& csv) {
    std::ostringstream json;
    json << '[';
    std::istringstream input(csv);
    std::string item;
    bool first = true;
    while (std::getline(input, item, ',')) {
        if (!first) json << ',';
        first = false;
        json << '"' << item << '"';
    }
    json << ']';
    return json.str();
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

std::int64_t RuntimeStatusStore::CeilingBoundary(std::int64_t now_us) {
    return ((now_us + kBarIntervalUs - 1) / kBarIntervalUs) * kBarIntervalUs;
}

bool RuntimeStatusStore::StartRun(const DailyBarStore& market) {
    sqlite3* db = nullptr;
    try {
        db = Open(path_);
        const bool empty = Scalar(db, "SELECT count(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'") == "0";
        Exec(db, "BEGIN IMMEDIATE");
        if (empty) {
            Exec(db, std::string(kRunsSchema) + ";" + kCurrentSchema + ";" + kInstrumentSchema + ";" +
                     kHistorySchema + ";" + kHistoryIndexSchema + ";PRAGMA user_version=0;");
        }
        ValidateSchema(db);
        Statement run(db, "INSERT INTO runs(run_id,started_us,instruments,source) VALUES(?,?,?,?)");
        run.Text(1, market.RunId()); run.Number(2, market.StartedUs());
        run.Text(3, JsonInstruments(market.Instruments())); run.Text(4, market.Source()); run.Run();
        Exec(db, "COMMIT");
        sqlite3_close(db);
        started_ = true;
        current_interval_start_us_ = CeilingBoundary(market.StartedUs());
        last_wall_us_ = market.StartedUs();
        return true;
    } catch (const std::exception& error) {
        if (db) { sqlite3_exec(db, "ROLLBACK", nullptr, nullptr, nullptr); sqlite3_close(db); }
        ctp::Log("event=run_create_failed run_id=", market.RunId(), " message=\"", error.what(), "\"");
        return false;
    }
}

void RuntimeStatusStore::Observe(const RuntimeSnapshot& snapshot, const DailyBarStore& market,
                                 ProcessState state, std::int64_t now_us) {
    if (state == ProcessState::Starting || state == ProcessState::Running) last_active_state_ = state;
    if (now_us < last_wall_us_) {
        current_interval_start_us_ = CeilingBoundary(now_us);
        while (used_intervals_.count(current_interval_start_us_)) current_interval_start_us_ += kBarIntervalUs;
        last_wall_us_ = now_us;
        return;
    }
    last_wall_us_ = now_us;
    if (now_us < current_interval_start_us_ + kBarIntervalUs) return;
    const auto completed = (now_us - current_interval_start_us_) / kBarIntervalUs;
    if (completed != 1) {
        current_interval_start_us_ = CeilingBoundary(now_us);
        while (used_intervals_.count(current_interval_start_us_)) current_interval_start_us_ += kBarIntervalUs;
        return;
    }
    HistoryRow row;
    row.interval_start_us = current_interval_start_us_;
    row.interval_end_us = row.interval_start_us + kBarIntervalUs;
    row.observed_us = now_us;
    row.state = last_active_state_;
    row.connected = snapshot.session.connected;
    row.logged_in = snapshot.session.logged_in;
    row.target_count = snapshot.session.instruments.size();
    for (const auto& item : snapshot.session.instruments) {
        row.subscribed_count += snapshot.session.logged_in && item.second.subscription == Subscription::Subscribed;
        row.subscription_failed += item.second.subscription == Subscription::Failed;
    }
    if (const auto it = snapshot.aggregation.runtime_ticks_by_interval.find(row.interval_start_us);
        it != snapshot.aggregation.runtime_ticks_by_interval.end()) row.tick_count = it->second;
    if (const auto it = market.RuntimeCommits().find(row.interval_start_us); it != market.RuntimeCommits().end()) {
        row.market_bar_count = it->second.bars;
        row.partial_bar_count = it->second.partial_bars;
    }
    row.last_tick_received_us = snapshot.aggregation.last_tick_received_us;
    row.last_market_commit_us = market.LastCommitUs();
    if (used_intervals_.insert(row.interval_start_us).second) pending_.push_back(row);
    current_interval_start_us_ += kBarIntervalUs;
}

bool RuntimeStatusStore::Publish(const RuntimeSnapshot& snapshot, const DailyBarStore& market,
                                ProcessState state, std::int64_t heartbeat_us) {
    if (!started_) {
        ctp::Log("event=status_write_failed run_id=", market.RunId(), " message=\"run not created\"");
        return false;
    }
    Observe(snapshot, market, state, heartbeat_us);
    sqlite3* db = nullptr;
    try {
        db = Open(path_);
        ValidateSchema(db);
        Exec(db, "BEGIN IMMEDIATE");
        for (const auto& value : pending_) {
            Statement row(db, "INSERT INTO runtime_snapshots VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)");
            int n = 1;
            row.Text(n++, market.RunId()); row.Number(n++, value.interval_start_us); row.Number(n++, value.interval_end_us);
            row.Number(n++, value.observed_us); row.Text(n++, ProcessStateName(value.state));
            row.Number(n++, value.connected); row.Number(n++, value.logged_in); row.Number(n++, value.target_count);
            row.Number(n++, value.subscribed_count); row.Number(n++, value.subscription_failed);
            row.Number(n++, value.tick_count); row.Number(n++, value.market_bar_count); row.Number(n++, value.partial_bar_count);
            row.Time(n++, value.last_tick_received_us); row.Time(n++, value.last_market_commit_us); row.Run();
        }
        const auto& session = snapshot.session;
        const auto& stats = snapshot.aggregation;
        std::int64_t subscribed = 0, failed = 0;
        const bool active = state == ProcessState::Starting || state == ProcessState::Running;
        for (const auto& item : session.instruments) {
            subscribed += active && session.logged_in && item.second.subscription == Subscription::Subscribed;
            failed += active && item.second.subscription == Subscription::Failed;
        }
        Exec(db, "DELETE FROM current_status;DELETE FROM instrument_status");
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
        if (!active) {
            Statement finish(db, "UPDATE runs SET ended_us=?,terminal_state=? WHERE run_id=? AND ended_us IS NULL");
            finish.Number(1, heartbeat_us); finish.Text(2, ProcessStateName(state)); finish.Text(3, market.RunId()); finish.Run();
            if (sqlite3_changes(db) != 1) throw std::runtime_error("run termination identity mismatch");
        }
        Exec(db, "COMMIT");
        sqlite3_close(db);
        pending_.clear();
        return true;
    } catch (const std::exception& error) {
        if (db) { sqlite3_exec(db, "ROLLBACK", nullptr, nullptr, nullptr); sqlite3_close(db); }
        ctp::Log("event=status_write_failed run_id=", market.RunId(), " message=\"", error.what(), "\"");
        return false;
    }
}
} // namespace collector
