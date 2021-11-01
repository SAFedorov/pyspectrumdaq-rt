import os
from setuptools import setup, find_packages

setup(
    name="pyspectrumdaq",
    version="0.8.0",
    author="Ivan Galinskiy",
    packages=find_packages(),
    include_package_data=True,
    package_data={"": [os.path.join("rsc", "*")]}
)
