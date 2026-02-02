#!/usr/bin/env bash

directory=$(dirname "$(realpath "$0")")

if [[ -n "$1" ]]; then
  echo "Rebuilding all in '$directory/*$1*'"
  for config in "$directory"/*"$1"*/config; do
    "$config"
  done
else
  echo "Rebuilding all in '$directory'"

  for config in "$directory"/*/config; do
    yes | "$config"
  done
fi

"$directory"/merge.bash
