"""
Setup script for Project Faraday.
"""

from setuptools import setup, find_packages
import os

# Read README if it exists
long_description = ""
if os.path.exists("README.md"):
    with open("README.md", "r", encoding="utf-8") as fh:
        long_description = fh.read()

setup(
    name="project-faraday",
    version="3.0.0",
    author="Project Faraday Contributors",
    description="An offline-first password vault for storing credentials and cryptocurrency addresses",
    long_description=long_description if long_description else "An offline-first password vault",
    long_description_content_type="text/markdown" if long_description else None,
    url="https://github.com/puretechteam/project-faraday",
    packages=find_packages(exclude=("tests", "tests.*")),
    package_data={
        "faraday.qt": ["resources/icons/lucide/*.svg", "resources/icons/lucide/LICENSE-lucide.txt"],
        "faraday.generator": ["eff_large_wordlist.txt", "WORDLIST_ATTRIBUTION.md"],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: End Users/Desktop",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Topic :: Security",
        "Topic :: Security :: Cryptography",
        "Topic :: Utilities",
    ],
    python_requires=">=3.10",
    install_requires=[
        "argon2-cffi>=23,<25",
        "cryptography>=41,<43",
        "cbor2>=5.4,<6.0",
        "PySide6>=6.8,<7",
    ],
    entry_points={
        "console_scripts": [
            "faraday=faraday.__main__:main",
        ],
        "gui_scripts": [
            "faraday-gui=faraday.qt.app:main",
        ],
    },
)

