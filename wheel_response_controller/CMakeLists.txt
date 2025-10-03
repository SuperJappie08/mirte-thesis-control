cmake_minimum_required(VERSION 3.8)
project(wheel_response_controller)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# find dependencies
find_package(ament_cmake_auto REQUIRED)
ament_auto_find_build_dependencies()

generate_parameter_library(wheel_response_controller_parameters
  src/wheel_response_controller_parameters.yaml
  include/wheel_response_controller/validators.hpp)
list(APPEND ${PROJECT_NAME}_LIBRARIES "wheel_response_controller_parameters")

generate_parameter_library(step_response_controller_parameters
  src/step_response_controller_parameters.yaml
  include/wheel_response_controller/validators.hpp)
list(APPEND ${PROJECT_NAME}_LIBRARIES "step_response_controller_parameters")

ament_auto_add_library(${PROJECT_NAME} SHARED
  src/wheel_response_controller.cpp
  src/step_response_controller.cpp
)

pluginlib_export_plugin_description_file(controller_interface wheel_response_controller.xml)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)

  ament_lint_auto_find_test_dependencies()
endif()

ament_auto_package(USE_SCOPED_HEADER_INSTALL_DIR)
