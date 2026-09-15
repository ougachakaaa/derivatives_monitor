#pragma once
#include "test.hpp"
#include <sqlite3.h>
#include <filesystem>
#include <unistd.h>
struct TempDirectory {
    std::filesystem::path path;
    TempDirectory() {
        char pattern[] = "/tmp/dm-collector-test-XXXXXX";
        const char* result = mkdtemp(pattern); CHECK(result); path = result;
    }
    ~TempDirectory() { std::error_code error; std::filesystem::remove_all(path, error); }
};
struct TestDb {
    sqlite3* db = nullptr;
    explicit TestDb(const std::filesystem::path& path, bool readonly = true) {
        CHECK(sqlite3_open_v2(path.c_str(), &db, readonly ? SQLITE_OPEN_READONLY : SQLITE_OPEN_READWRITE, nullptr) == SQLITE_OK);
    }
    ~TestDb() { sqlite3_close(db); }
    void Exec(const std::string& sql) { CHECK(sqlite3_exec(db, sql.c_str(), nullptr, nullptr, nullptr) == SQLITE_OK); }
    void Rejects(const std::string& sql) { CHECK(sqlite3_exec(db, sql.c_str(), nullptr, nullptr, nullptr) != SQLITE_OK); }
    std::string Scalar(const std::string& sql) {
        sqlite3_stmt* stmt = nullptr;
        CHECK(sqlite3_prepare_v2(db, sql.c_str(), -1, &stmt, nullptr) == SQLITE_OK);
        CHECK(sqlite3_step(stmt) == SQLITE_ROW);
        const auto* text = sqlite3_column_text(stmt, 0);
        std::string value = text ? reinterpret_cast<const char*>(text) : "NULL";
        CHECK(sqlite3_finalize(stmt) == SQLITE_OK);
        return value;
    }
};
