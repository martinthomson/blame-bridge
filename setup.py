#!/usr/bin/env python
from setuptools import setup
from blame_bridge.__version__ import __version__

setup(
    name='blame_bridge',
    version=__version__,
    author='Martin Thomson',
    author_email='martin.thomson@gmail.com',
    scripts=['blame-bridge'],
    packages=['blame_bridge'],
    description='Blame Bridge for git',
    long_description='Reformat Files, Maintain Blame',
    install_requires=[
        'requests'
    ],
    url='https://github.com/martinthomson/blame-bridge',
    license='MIT'
)
