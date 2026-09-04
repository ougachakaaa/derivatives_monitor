#!/usr/bin/env bash

set -euo pipefail

usage() {
    echo "Usage: $0 [Debug|Release]" >&2
}

build_type="${1:-Release}"
if [[ $# -gt 1 ]] || [[ "$build_type" != "Debug" && "$build_type" != "Release" ]]; then
    usage
    exit 2
fi

for tool_name in cmake g++ ldd; do
    if ! command -v "$tool_name" >/dev/null 2>&1; then
        echo "Error: required build tool is unavailable: $tool_name" >&2
        exit 1
    fi
done

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly source_dir="$(cd -- "$script_dir/.." && pwd)"
readonly build_dir="$source_dir/build/$build_type"
readonly executable="$build_dir/bin/ctp_md"

cmake -S "$source_dir" -B "$build_dir" -DCMAKE_BUILD_TYPE="$build_type"
cmake --build "$build_dir" --parallel "$(nproc)"

if [[ ! -x "$executable" ]]; then
    echo "Error: build completed without producing $executable" >&2
    exit 1
fi

if ldd "$executable" | grep -q 'not found'; then
    echo "Error: the executable has unresolved shared-library dependencies:" >&2
    ldd "$executable" >&2
    exit 1
fi

echo "Linux CTP market-data client built successfully: $executable"
