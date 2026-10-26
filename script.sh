#!/bin/bash

current_dir=$(dirname "$0")
cd "$current_dir" || exit 1

echo current_dir: "$current_dir"

running_tests=$(pytest --maxfail=1 --disable-warnings -q tests/)
echo "Running tests..."
echo "Tests result: $running_tests"

