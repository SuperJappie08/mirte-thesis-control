import sys

from glob import glob
from setuptools import find_packages, setup

package_name = "wheel_response_recorder"

if len(sys.argv) >= 2 and sys.argv[1] != "clean":
    from generate_parameter_library_py.setup_helper import generate_parameter_module

    # set module_name and yaml file
    module_name = "response_director_parameters"
    yaml_file = f"{package_name}/response_director_parameters.yaml"
    validation_module = f"{package_name}.parameter_validation"
    generate_parameter_module(
        module_name, yaml_file, validation_module=validation_module
    )


config_files = [
    (f"share/{package_name}/{folder}", glob(folder + "/*"))
    for folder in glob("config/*")
]

setup(
    name=package_name,
    version="0.0.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (f"share/{package_name}/launch", glob("launch/*")),
    ]
    + config_files,
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Jasper van Brakel",
    maintainer_email="36795178+SuperJappie08@users.noreply.github.com",
    description="TODO: Package description",
    license="Apache-2.0",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "response_director = wheel_response_recorder.response_director:main",
            # "response_director_old = wheel_response_recorder.response_director_node:main",
        ],
    },
)
