from setuptools import find_packages
from setuptools import setup

package_name = 'thesis_data_processing'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Jasper van Brakel',
    maintainer_email='36795178+SuperJappie08@users.noreply.github.com',
    description='TODO: Package description',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            f'bodeplotter = {package_name}.bodeplot:main',
            f'step_response = {package_name}.step_response:main',
        ],
    },
)
