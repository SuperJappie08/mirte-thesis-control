#!/usr/bin/env python3
# Copyright 2025, Jasper van Brakel
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import time
import itertools

from tqdm.contrib.itertools import product as tqdm_product

import rclpy

from wheel_response_recorder.parameter_iterator import ParameterIterator
from wheel_response_recorder.response_director_parameters import (
    response_director as response_director_parameters,
)

def main(args=None):
    rclpy.init(args=args)

    try:
        node = rclpy.create_node("response_director")

        param_listener = response_director_parameters.ParamListener(node)
        params = param_listener.get_params()

        product = tqdm_product if params.progressbar else itertools.product


        offset = ParameterIterator("offset", params.sinusoid)
        amplitude = ParameterIterator("amplitude", params.sinusoid)
        frequency = ParameterIterator("frequency", params.sinusoid)
        phase = ParameterIterator("phase", params.sinusoid)

        for (o, a, f,p) in product(offset, amplitude, frequency, phase):
            time.sleep(params.measurement_duration)
            # print(o, a, f, p)

    finally:
        node.destroy_node()

    rclpy.try_shutdown()


if __name__ == "__main__":
    main()
