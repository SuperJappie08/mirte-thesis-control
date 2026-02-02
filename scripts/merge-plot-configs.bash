#!/usr/bin/env bash

directory=$(dirname "$(realpath "$0")")

source /home/jap/thesis/ths_ws/install/setup.bash

yes | ros2 run thesis_data_processing plot_config_merger --input "$directory"/*/plot-config.pkl --output "$directory"/merged-plot-config.pkl
