#!/usr/bin/env bash

set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly source_dir="$(cd -- "$script_dir/.." && pwd)"
readonly executable="$source_dir/build/Release/bin/ctp_md"

if [[ ! -x "$executable" ]]; then
    echo "Error: Linux executable is missing: $executable" >&2
    echo "Build it first: $script_dir/build.sh Release" >&2
    exit 1
fi

config="$source_dir/config.ini"
if [[ ! -f "$config" ]]; then
    config="$source_dir/config.example.ini"
    echo "Notice: using example configuration: $config" >&2
fi

cd -- "$source_dir"
exec "$executable" --config "$config" "$@"
