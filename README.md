# mirte-thesis-control
> ROS packages for analysing the system responses of a `ros2_control`-based control system.

## Building
To build the packages in this repository run the following commands:
```bash
source /opt/ros/jazzy/setup.bash
mkdir -p ths_ws/src
cd ths_ws/src
git clone https://github.com/SuperJappie08/mirte-thesis-control.git
cd ..
vcs import < mirte-thesis-control/sources.repos
cd ..
rosdep install --from-paths src --ignore-src -ry
colcon build # Optionally with --symlink-install and mixins
```

## Preparing the MIRTE/Robot
The controllers need to be build on the robot in order to function properly. (Assuming the robot is a MIRTE Master)
Run the following commands on the MIRTE:
```bash
cd mirte_ws/src
git clone https://github.com/SuperJappie08/mirte-thesis-control.git
touch mirte-thesis-control/thesis_data_processing/COLCON_IGNORE  # Processing does not need to happen on the robot
cd ..
rosdep install --from-paths src --ignore-src -ry
colcon build --packages-select wheel_response_controller wheel_response_recorder --mixin rel-with-deb-info
```

## Pre-measurement
The MIRTE control system has been patched in such a way that the configuration can be controlled with the following environment variables in `.mirte_settings.sh`:

|                      ENV                       | Purpose                                                                                                                          |
| :--------------------------------------------: | :------------------------------------------------------------------------------------------------------------------------------  |
|             `MIRTE_CONTROL_METHOD`             | Can be `old` or `new` to toggle between setups (requires ROS restart)                                                            |
| `MIRTE_CONTROL_THESIS_CONTROLLER_MANAGER_RATE` | \[NEW SETUP\] To control the frequency of all controllers and hardware interfaces (defaults to 10)                               |
|  `MIRTE_CONTROL_THESIS_BASE_CONTROLLER_RATE`   | \[NEW SETUP\] To control the frequency of the base controllers and hardware interfaces (defaults to the controller manager rate) |
|   `MIRTE_CONTROL_THESIS_ARM_CONTROLLER_RATE`   | \[NEW SETUP\] To control the frequency of the arm controllers and hardware interfaces (defaults to the controller manager rate) |

## Measuring Frequency Response
In order to measure the frequency response, run the following command on the robot:
```bash
ros2 launch wheel_response_recorder prepare_frequency.launch.xml control_setup:=<service_based or topic_based>  # record_diagnostics:=<BOOL>  # Optional, default False
```

After this, the recording can be made on an external machine or the robot by running:
```bash
ros2 launch wheel_response_recorder frequency_prelim.launch.xml -s # To inspect the options
# Various options are available
ros2 launch wheel_response_recorder frequency_prelim.launch.xml hw_interface:=<service_based or multimotor_topic_based> sinusoid_param_file:=<ONE OF THE OPTIONS> ...
# For example
ros2 launch wheel_response_recorder frequency_prelim.launch.xml hw_interface:='multimotor_topic_based' measurement_postfix:="R20" measurements_folder:=~/thesis/measurements/experimental/ extra_notes:="lifted, updates, cm-rate 20 (arm 10), with recording delay" sinusoid_param_file:=prelim_frequency_{zero,offset}.yaml
```

## Measuring Step Response
In order to measure the step response, run the following command on the robot:
```bash
ros2 launch wheel_response_recorder prepare_step.launch.xml control_setup:=<service_based or topic_based>  # record_diagnostics:=<BOOL>  # Optional, default False
```

After this, the recording can be made on an external machine or the robot by running:
```bash
ros2 launch wheel_response_recorder frequency_prelim.launch.xml -s # To inspect the options
# Various options are available
ros2 launch wheel_response_recorder frequency_prelim.launch.xml hw_interface:=<service_based or multimotor_topic_based> sinusoid_param_file:=<ONE OF THE OPTIONS> ...

# For example
ros2 launch wheel_response_recorder step_response.launch.xml hw_interface:='multimotor_topic_based' measurement_postfix:="R20" measurements_folder:=~/thesis/measurements/experimental/floor2/ extra_notes:="floored, cm-rate 20 (arm 10), with recording delay and pausing, with stats and diag" manual:=True measurement_duration:=4.0
```

Or record correction data with the same preparation setups
```bash
ros2 launch wheel_response_recorder step_zero_frequency_correction.launch.xml -s  # To inspect the options
# Various options are available
ros2 launch wheel_response_recorder step_zero_frequency_correction.launch.xml hw_interface:=<service_based or multimotor_topic_based> ...

# For example
ros2 launch wheel_response_recorder step_zero_frequency_correction.launch.xml hw_interface:='multimotor_topic_based' measurement_postfix:="R20" measurements_folder:=~/thesis/measurements/experimental/correction/ extra_notes:="lifted, cm-rate 20 (arm 10), with recording delay"
```


## Development
This repo uses CI and pre-commit to validate commits.
To install the correct pre-commit hooks run the following:
```shell
  pre-commit install
```
