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
)
list(APPEND ${PROJECT_NAME}_LIBRARIES "wheel_response_controller_parameters")

ament_auto_add_library(${PROJECT_NAME} SHARED
  src/wheel_response_controller.cpp
)

pluginlib_export_plugin_description_file(controller_interface wheel_response_controller.xml)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  # the following line skips the linter which checks for copyrights
  # comment the line when a copyright and license is added to all source files
  set(ament_cmake_copyright_FOUND TRUE)
  # the following line skips cpplint (only works in a git repo)
  # comment the line when this package is in a git repo and when
  # a copyright and license is added to all source files
  set(ament_cmake_cpplint_FOUND TRUE)
  ament_lint_auto_find_test_dependencies()
endif()

ament_auto_package(USE_SCOPED_HEADER_INSTALL_DIR)
