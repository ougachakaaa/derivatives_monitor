#pragma once

#include "ingestion/session.hpp"
#include "persistence/sqlite_store.hpp"

namespace collector {

enum class ProcessState { Starting, Running, Stopped, Failed };

const char* ProcessStateName(ProcessState state);
bool PublishHealth(const std::filesystem::path& directory, const SessionStatus& session,
                   const AggregationStats& aggregation, const DailyBarStore& store, ProcessState state);

} // namespace collector
