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

#include <control_toolbox/sinusoid.hpp>
#include <controller_interface/controller_interface.hpp>
#include <controller_interface/controller_interface_base.hpp>
#include <controller_interface/helpers.hpp>
#include <rclcpp_lifecycle/state.hpp>
#include <wheel_response_controller/wheel_response_controller.hpp>

namespace wheel_response_controller
{

// FIXME(SuperJappie08): Maybe remove explicit constructor
WheelResponseController::WheelResponseController()
: controller_interface::ControllerInterface(), sinusoid_()
{
}

controller_interface::InterfaceConfiguration
WheelResponseController::command_interface_configuration() const
{
  return {
    controller_interface::interface_configuration_type::INDIVIDUAL,
    {params_.command_joint_name + "/" + params_.interface_name}};
}

controller_interface::InterfaceConfiguration
WheelResponseController::state_interface_configuration() const
{
  return {
    controller_interface::interface_configuration_type::INDIVIDUAL,
    {params_.state_joint_name + "/" + params_.interface_name}};
}

controller_interface::CallbackReturn WheelResponseController::on_init()
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
controller_interface::CallbackReturn WheelResponseController::on_activate(
  const rclcpp_lifecycle::State & /*previous_state*/)
{
  params_ = param_listener_->get_params();

  // TODO(SuperJappie08): Temporary initialization of sinusiod_
  sinusoid_ = control_toolbox::Sinusoid(
    params_.sinusoid.offset, params_.sinusoid.amplitude, params_.sinusoid.frequency,
    params_.sinusoid.phase);

  return controller_interface::CallbackReturn::SUCCESS;
}

// FIXME(SuperJappie08): Check if hw interface is smart enough, or add stopping behavior

controller_interface::return_type WheelResponseController::update(
  const rclcpp::Time & time, const rclcpp::Duration & period)
{
  // NOTE(SuperJappie08): Could use something like this to update frequency.
  // param_listener_->try_get_params(params_);

  // FIXME(SuperJappie08): Implement
  (void)period;

  double q, qd, qdd;
  q = sinusoid_.update(time.seconds(), qd, qdd);

  (void)command_interfaces_[0].set_value(q);
  // controller_interface:

  return controller_interface::return_type::OK;
}

}  // namespace wheel_response_controller

#include <pluginlib/class_list_macros.hpp>

PLUGINLIB_EXPORT_CLASS(
  wheel_response_controller::WheelResponseController, controller_interface::ControllerInterface)
