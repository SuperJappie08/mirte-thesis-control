// Copyright 2025, Jasper van Brakel
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

#include <vector>

// Package includes
#include <wheel_response_controller/step_response_controller.hpp>

// ROS2 Control
#include <controller_interface/controller_interface.hpp>
#include <controller_interface/helpers.hpp>

// General ROS includes
#include <rclcpp/duration.hpp>
#include <rclcpp/logging.hpp>
#include <rclcpp/time.hpp>
#include <rclcpp_lifecycle/state.hpp>

namespace wheel_response_controller
{

// FIXME(SuperJappie08): Maybe remove explicit constructor
StepResponseController::StepResponseController()
: controller_interface::ControllerInterface() {}

controller_interface::InterfaceConfiguration
StepResponseController::command_interface_configuration() const
{
  std::vector<std::string> command_interfaces;
  for (const auto & command_joint_name : params_.command_joint_names) {
    command_interfaces.push_back(command_joint_name + "/" + params_.interface_name);
  }

  return {controller_interface::interface_configuration_type::INDIVIDUAL, command_interfaces};
}

controller_interface::InterfaceConfiguration
StepResponseController::state_interface_configuration() const
{
  std::vector<std::string> state_interfaces;
  for (const auto & state_joint_name : params_.state_joint_names) {
    state_interfaces.push_back(state_joint_name + "/" + params_.interface_name);
  }

  return {controller_interface::interface_configuration_type::INDIVIDUAL, state_interfaces};
}

controller_interface::CallbackReturn StepResponseController::on_init()
{
  try {
    // Create the parameter listener and get the parameters
    param_listener_ = std::make_shared<ParamListener>(get_node());
    params_ = param_listener_->get_params();
  } catch (const std::exception & e) {
    fprintf(stderr, "Exception thrown during init stage with message: %s \n", e.what());
    return controller_interface::CallbackReturn::ERROR;
  }

  return controller_interface::CallbackReturn::SUCCESS;
}

// NOTE(SuperJappie08): This was on_configure, however a controller can not be
//                      transitioned into unconfigured.
controller_interface::CallbackReturn StepResponseController::on_activate(
  const rclcpp_lifecycle::State & /*previous_state*/)
{
  param_listener_->try_get_params(params_);

  start_time_ = get_node()->now();

  return controller_interface::CallbackReturn::SUCCESS;
}

controller_interface::CallbackReturn StepResponseController::on_deactivate(
  const rclcpp_lifecycle::State & /*previous_state*/)
{
  auto logger = get_node()->get_logger();
  param_listener_->try_get_params(params_);

  RCLCPP_INFO(logger, "Deactivating '%s'", get_name().c_str());

  // NOTE(SuperJappie08): Set the control input back to zero to prevent
  //                      leaving it at a continuous speed
  auto reset_value = params_.reset_command_on_deactivate;
  if (!std::isnan(reset_value)) {
    RCLCPP_INFO(logger, "Resetting the command interface(s) to %lf", reset_value);

    bool set_command_result = true;
    for (auto & command_interface : command_interfaces_) {
      set_command_result &= command_interface.set_value(reset_value);
    }

    RCLCPP_WARN_EXPRESSION(
      logger, !set_command_result, "Some reset commands were unable to be reset!");
  }

  return controller_interface::CallbackReturn::SUCCESS;
}

controller_interface::return_type StepResponseController::update(
  const rclcpp::Time & time, const rclcpp::Duration & /*period*/)
{
  auto logger = get_node()->get_logger();

  auto current_time = time - start_time_;

  double q;
  if (current_time.seconds() < params_.step.t_step) {
    q = params_.step.initial_commmand;
  } else {
    q = params_.step.step_command;
  }

  bool set_command_result = true;
  for (auto & command_interface : command_interfaces_) {
    set_command_result &= command_interface.set_value(q);
  }

  RCLCPP_WARN_EXPRESSION(logger, !set_command_result, "Some commands were unable to be set!");

  return controller_interface::return_type::OK;
}

}  // namespace wheel_response_controller

#include <pluginlib/class_list_macros.hpp>

PLUGINLIB_EXPORT_CLASS(
  wheel_response_controller::StepResponseController, controller_interface::ControllerInterface)
