#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
case "$(uname -s)" in Darwin) ext=dylib;; Linux) ext=so;; *) echo "Unsupported platform" >&2; exit 1;; esac
cxx=${CXX:-c++}
"$cxx" -O3 -std=c++17 -pthread -fPIC -shared -Iinclude src/cloudsentinel.cpp -o libcloudsentinel.$ext
mkdir -p build
"$cxx" -O3 -std=c++17 -pthread -Iinclude benchmarks/bench_engine.cpp -L. -lcloudsentinel -Wl,-rpath,"$PWD" -o build/bench_engine
./build/bench_engine
