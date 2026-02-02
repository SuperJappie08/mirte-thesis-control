#!/usr/bin/env bash

directory=$(dirname "$(realpath "$0")")
thesis_directory=$(dirname "$directory" )

while [[ "${thesis_directory##*/}" != "thesis" ]]; do
  thesis_directory=$(dirname "$thesis_directory")
done

"$thesis_directory"/plot-configs/"${directory##*/}"/rebuild.bash

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
