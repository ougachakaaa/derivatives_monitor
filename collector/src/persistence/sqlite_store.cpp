#include "persistence/sqlite_store.hpp"

#include <fcntl.h>
#include <sys/file.h>
#include <unistd.h>

#include <algorithm>
#include <iomanip>
#include <optional>
#include <random>
#include <sstream>
#include <tuple>
#include <type_traits>

namespace collector {
namespace {

void Check(sqlite3* db, int rc) {
    if (rc != SQLITE_OK) throw std::runtime_error("SQLite: " + std::string(db ? sqlite3_errmsg(db) : sqlite3_errstr(rc)));
}

void Exec(sqlite3* db, const std::string& sql) {
    char* message = nullptr;
    const int rc = sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &message);
    if (rc != SQLITE_OK) {
        const std::string detail = message ? message : sqlite3_errmsg(db);
        sqlite3_free(message);
        throw std::runtime_error("SQLite: " + detail);
    }
}

class Statement {
public:
    Statement(sqlite3* db, const std::string& sql) : db_(db) {
        Check(db_, sqlite3_prepare_v2(db_, sql.c_str(), -1, &stmt_, nullptr));
    }
    ~Statement() { sqlite3_finalize(stmt_); }
    void Bind(int n, const std::string& value) {
        Check(db_, sqlite3_bind_text(stmt_, n, value.data(), static_cast<int>(value.size()), SQLITE_TRANSIENT));
    }
    template<std::size_t N> void Bind(int n, const char (&value)[N]) { Bind(n, ctp::FieldString(value)); }
    void Bind(int n, std::int64_t value) { Check(db_, sqlite3_bind_int64(stmt_, n, value)); }
    void Bind(int n, int value) { Bind(n, static_cast<std::int64_t>(value)); }
    void Bind(int n, double value) {
        Check(db_, ValidNumber(value) ? sqlite3_bind_double(stmt_, n, value) : sqlite3_bind_null(stmt_, n));
    }
    template<class T> void Bind(int n, const std::optional<T>& value) {
        if (value) Bind(n, *value);
        else Check(db_, sqlite3_bind_null(stmt_, n));
    }
    void Run() {
        const int rc = sqlite3_step(stmt_);
        if (rc != SQLITE_DONE) Check(db_, rc);
        Check(db_, sqlite3_reset(stmt_));
        Check(db_, sqlite3_clear_bindings(stmt_));
    }
    std::string Scalar() {
        const int rc = sqlite3_step(stmt_);
        if (rc != SQLITE_ROW) {
            if (rc != SQLITE_DONE) Check(db_, rc);
            throw std::runtime_error("SQLite: missing metadata");
        }
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

bool CanonicalFact(const char* name) {
    return std::string(name) == "TradingDay" || std::string(name) == "InstrumentID";
}

const std::string& DatasetSchema() {
    static const std::string schema =
        "CREATE TABLE dataset(singleton INTEGER PRIMARY KEY CHECK(singleton=1),"
        "trading_day TEXT NOT NULL,schema_version INTEGER NOT NULL CHECK(schema_version=2),"
        "bar_interval_us INTEGER NOT NULL CHECK(bar_interval_us=15000000),"
        "close_grace_us INTEGER NOT NULL CHECK(close_grace_us=1000000))";
    return schema;
}

const std::string& RunsSchema() {
    static const std::string schema =
        "CREATE TABLE runs(run_id TEXT PRIMARY KEY,started_us INTEGER NOT NULL,stopped_us INTEGER,"
        "last_commit_us INTEGER,instruments TEXT NOT NULL,source TEXT NOT NULL)";
    return schema;
}

std::string MarketBarTableSchema(const std::string& day) {
    std::string schema =
        "CREATE TABLE market_bars("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "run_id TEXT NOT NULL REFERENCES runs(run_id),"
        "TradingDay TEXT NOT NULL CHECK(TradingDay='" + day + "'),"
        "InstrumentID TEXT NOT NULL,"
        "bucket_start_us INTEGER NOT NULL CHECK(bucket_start_us%15000000=0),"
        "bucket_end_us INTEGER NOT NULL CHECK(bucket_end_us=bucket_start_us+15000000),"
        "bar_open REAL,bar_high REAL,bar_low REAL,bar_close REAL,"
        "bar_volume INTEGER,bar_turnover REAL,"
        "callback_count INTEGER NOT NULL CHECK(callback_count>0),"
        "valid_last_price_count INTEGER NOT NULL CHECK(valid_last_price_count>=0 AND valid_last_price_count<=callback_count),"
        "first_event_us INTEGER NOT NULL,last_event_us INTEGER NOT NULL,"
        "first_received_us INTEGER NOT NULL,last_received_us INTEGER NOT NULL,close_received_us INTEGER NOT NULL,"
        "committed_us INTEGER NOT NULL,"
        "is_partial INTEGER NOT NULL CHECK(is_partial IN(0,1)),"
        "partial_reasons TEXT NOT NULL CHECK((is_partial=0 AND partial_reasons='[]') OR (is_partial=1 AND partial_reasons!='[]'))";
    VisitFacts(CThostFtdcDepthMarketDataField{}, [&](const char* name, const auto& value) {
        if (CanonicalFact(name)) return;
        using T = std::decay_t<decltype(value)>;
        schema += std::string(",") + name + (std::is_floating_point_v<T> ? " REAL" : std::is_integral_v<T> ? " INTEGER" : " TEXT");
    });
    schema +=
        ",CHECK(first_event_us>=bucket_start_us AND first_event_us<=last_event_us AND last_event_us<bucket_end_us)"
        ",CHECK(first_received_us<=last_received_us)"
        ",CHECK((valid_last_price_count=0 AND bar_open IS NULL AND bar_high IS NULL AND bar_low IS NULL AND bar_close IS NULL)"
        " OR (valid_last_price_count>0 AND bar_open IS NOT NULL AND bar_high IS NOT NULL AND bar_low IS NOT NULL AND bar_close IS NOT NULL"
        " AND bar_high>=bar_open AND bar_high>=bar_close AND bar_low<=bar_open AND bar_low<=bar_close AND bar_high>=bar_low))"
        ",UNIQUE(TradingDay,InstrumentID,bucket_start_us))";
    return schema;
}

const std::string& MarketBarIndexSchema() {
    static const std::string schema =
        "CREATE INDEX market_bars_instrument_bucket ON market_bars(InstrumentID,bucket_start_us,id)";
    return schema;
}

void ValidateSchema(sqlite3* db, const std::string& day) {
    if (Scalar(db, "SELECT count(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'") != "3" ||
        Scalar(db, "SELECT sql FROM sqlite_master WHERE type='table' AND name='dataset'") != DatasetSchema() ||
        Scalar(db, "SELECT sql FROM sqlite_master WHERE type='table' AND name='runs'") != RunsSchema() ||
        Scalar(db, "SELECT sql FROM sqlite_master WHERE type='table' AND name='market_bars'") != MarketBarTableSchema(day) ||
        Scalar(db, "SELECT sql FROM sqlite_master WHERE type='index' AND name='market_bars_instrument_bucket'") != MarketBarIndexSchema())
        throw std::runtime_error("SQLite physical schema mismatch");
}

} // namespace

DailyBarStore::DailyBarStore(std::filesystem::path directory, const std::vector<std::string>& instruments, std::string source)
    : directory_(std::move(directory)), run_id_(NewRunId()), source_(std::move(source)) {
    for (const auto& id : instruments) {
        if (!instruments_.empty()) instruments_ += ',';
        instruments_ += id;
        instrument_stats_.emplace(id, InstrumentStoreStats{});
    }
    std::filesystem::create_directories(directory_);
    lock_fd_ = ::open((directory_ / ".collector.lock").c_str(), O_CREAT | O_RDWR | O_CLOEXEC, 0600);
    if (lock_fd_ < 0) throw std::runtime_error("cannot open collector data-directory lock");
    if (flock(lock_fd_, LOCK_EX | LOCK_NB) != 0) {
        ::close(lock_fd_);
        lock_fd_ = -1;
        throw std::runtime_error("data directory already owned by another collector");
    }
}

DailyBarStore::~DailyBarStore() {
    Close();
    if (lock_fd_ >= 0) ::close(lock_fd_);
}

void DailyBarStore::Close() noexcept {
    if (db_) {
        sqlite3_close_v2(db_);
        db_ = nullptr;
    }
    day_.clear();
}

void DailyBarStore::Open(const std::string& day) {
    if (day_ == day) return;
    if (!ValidTradingDay(day)) throw std::runtime_error("invalid storage trading day");
    Close();
    try {
        const auto path = directory_ / (day + ".sqlite");
        Check(db_, sqlite3_open_v2(path.c_str(), &db_, SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE, nullptr));
        Check(db_, sqlite3_busy_timeout(db_, 1000));
        const auto version = Scalar(db_, "PRAGMA user_version");
        const bool empty = Scalar(db_, "SELECT count(*) FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'") == "0";
        if (version != "2" && !(version == "0" && empty)) throw std::runtime_error("unsupported SQLite schema version");
        if (!empty && (Scalar(db_, "PRAGMA application_id") != "1145914161" ||
                       Scalar(db_, "SELECT trading_day FROM dataset WHERE singleton=1") != day))
            throw std::runtime_error("SQLite dataset identity/trading day mismatch");
        if (Scalar(db_, "PRAGMA journal_mode=WAL") != "wal") throw std::runtime_error("SQLite WAL unavailable");
        Exec(db_, "PRAGMA synchronous=FULL");
        Exec(db_, "PRAGMA foreign_keys=ON");
        Exec(db_, "BEGIN IMMEDIATE");
        if (empty) {
            Exec(db_, DatasetSchema() + ";INSERT INTO dataset VALUES(1,'" + day + "',2,15000000,1000000);" +
                RunsSchema() + ";PRAGMA application_id=1145914161;PRAGMA user_version=2;" +
                MarketBarTableSchema(day) + ";" + MarketBarIndexSchema() + ";");
        } else if (Scalar(db_, "SELECT schema_version||':'||bar_interval_us||':'||close_grace_us FROM dataset WHERE singleton=1") !=
                   "2:15000000:1000000") {
            throw std::runtime_error("SQLite dataset schema mismatch");
        }
        ValidateSchema(db_, day);
        Statement run(db_, "INSERT INTO runs(run_id,started_us,instruments,source) VALUES(?,?,?,?) ON CONFLICT(run_id) DO NOTHING");
        run.Bind(1, run_id_);
        run.Bind(2, started_us_);
        run.Bind(3, instruments_);
        run.Bind(4, source_);
        run.Run();
        Exec(db_, "COMMIT");
        day_ = day;
        touched_days_.insert(day);
        ctp::Log("event=sqlite_opened run_id=", run_id_, " trading_day=", day, " path=", path.string());
    } catch (...) {
        if (db_) sqlite3_exec(db_, "ROLLBACK", nullptr, nullptr, nullptr);
        Close();
        throw;
    }
}

std::uint64_t DailyBarStore::Write(const std::vector<MarketBar>& bars) {
    std::map<std::string, std::vector<const MarketBar*>> groups;
    for (const auto& bar : bars) {
        const auto day = ctp::FieldString(bar.close_facts.TradingDay);
        const auto instrument = ctp::FieldString(bar.close_facts.InstrumentID);
        if (!ValidTradingDay(day)) throw std::runtime_error("invalid Bar trading day");
        if (instrument.empty() || bar.bucket_end_us != bar.bucket_start_us + kBarIntervalUs ||
            bar.callback_count <= 0 || bar.is_partial != (bar.partial_reasons != "[]"))
            throw std::runtime_error("invalid Market Bar invariant");
        groups[day].push_back(&bar);
    }

    std::uint64_t total = 0;
    for (auto& group : groups) {
        std::sort(group.second.begin(), group.second.end(), [](const MarketBar* left, const MarketBar* right) {
            return std::make_tuple(ctp::FieldString(left->close_facts.InstrumentID), left->bucket_start_us) <
                   std::make_tuple(ctp::FieldString(right->close_facts.InstrumentID), right->bucket_start_us);
        });
        Open(group.first);
        std::string columns =
            "run_id,TradingDay,InstrumentID,bucket_start_us,bucket_end_us,bar_open,bar_high,bar_low,bar_close,"
            "bar_volume,bar_turnover,callback_count,valid_last_price_count,first_event_us,last_event_us,"
            "first_received_us,last_received_us,close_received_us,committed_us,is_partial,partial_reasons";
        std::string placeholders = "?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?";
        VisitFacts(CThostFtdcDepthMarketDataField{}, [&](const char* name, const auto&) {
            if (!CanonicalFact(name)) { columns += std::string(",") + name; placeholders += ",?"; }
        });
        const auto committed_us = NowUs();
        std::uint64_t inserted = 0, partial = 0;
        std::map<std::string, InstrumentStoreStats> per_instrument;
        try {
            Statement insert(db_, "INSERT INTO market_bars(" + columns + ") VALUES(" + placeholders + ")");
            Exec(db_, "BEGIN IMMEDIATE");
            for (const auto* bar : group.second) {
                const auto instrument = ctp::FieldString(bar->close_facts.InstrumentID);
                int i = 1;
                insert.Bind(i++, run_id_);
                insert.Bind(i++, group.first);
                insert.Bind(i++, instrument);
                insert.Bind(i++, bar->bucket_start_us);
                insert.Bind(i++, bar->bucket_end_us);
                insert.Bind(i++, bar->bar_open); insert.Bind(i++, bar->bar_high);
                insert.Bind(i++, bar->bar_low); insert.Bind(i++, bar->bar_close);
                insert.Bind(i++, bar->bar_volume); insert.Bind(i++, bar->bar_turnover);
                insert.Bind(i++, bar->callback_count); insert.Bind(i++, bar->valid_last_price_count);
                insert.Bind(i++, bar->first_event_us); insert.Bind(i++, bar->last_event_us);
                insert.Bind(i++, bar->first_received_us); insert.Bind(i++, bar->last_received_us);
                insert.Bind(i++, bar->close_received_us); insert.Bind(i++, committed_us);
                insert.Bind(i++, bar->is_partial ? 1 : 0); insert.Bind(i++, bar->partial_reasons);
                VisitFacts(bar->close_facts, [&](const char* name, const auto& value) {
                    if (!CanonicalFact(name)) insert.Bind(i++, value);
                });
                insert.Run();
                ++inserted;
                partial += bar->is_partial;
                ++per_instrument[instrument].bars_written;
                per_instrument[instrument].partial_bars += bar->is_partial;
            }
            Statement update(db_, "UPDATE runs SET last_commit_us=? WHERE run_id=?");
            update.Bind(1, committed_us); update.Bind(2, run_id_); update.Run();
            Exec(db_, "COMMIT");
        } catch (...) {
            sqlite3_exec(db_, "ROLLBACK", nullptr, nullptr, nullptr);
            throw;
        }
        bars_written_ += inserted;
        partial_bars_ += partial;
        total += inserted;
        last_commit_us_ = committed_us;
        for (const auto& item : per_instrument) {
            instrument_stats_[item.first].bars_written += item.second.bars_written;
            instrument_stats_[item.first].partial_bars += item.second.partial_bars;
        }
    }
    return total;
}

void DailyBarStore::Finish() {
    for (const auto& day : touched_days_) {
        Open(day);
        Exec(db_, "BEGIN IMMEDIATE");
        try {
            Statement stop(db_, "UPDATE runs SET stopped_us=? WHERE run_id=?");
            stop.Bind(1, NowUs()); stop.Bind(2, run_id_); stop.Run();
            Exec(db_, "COMMIT");
        } catch (...) {
            sqlite3_exec(db_, "ROLLBACK", nullptr, nullptr, nullptr);
            throw;
        }
    }
    Close();
}

} // namespace collector
