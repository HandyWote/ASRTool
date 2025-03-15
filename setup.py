from setuptools import setup, find_packages

setup(
    name="bk_asr",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "numpy",
        "scipy"
    ],
    author="BK",
    description="ASR Tools Package"
)