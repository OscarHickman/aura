from setuptools import setup, find_packages
import os

def read_requirements():
    if os.path.exists("requirements.txt"):
        with open("requirements.txt") as f:
            # Filter out comments and blank lines
            return [
                line.strip()
                for line in f
                if line.strip() and not line.strip().startswith("#")
            ]
    return []

setup(
    name="aura-recommender",
    version="0.1.0",
    description="AURA - Personalised arXiv Recommender",
    packages=find_packages(),
    py_modules=["run"],
    install_requires=read_requirements(),
    entry_points={
        "console_scripts": [
            "aura=run:main",
        ],
    },
)
