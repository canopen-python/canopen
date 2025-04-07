#!/usr/bin/env python
import os
from setuptools import setup
import subprocess

def get_version():
    """
    Get the version from a git tag

    Executes
        git tag |grep -Eo '[0-9]+\\.[0-9]+\\.[0-9]+' |sort | tail -1
    and returns the result
    """
    tag_proc = subprocess.Popen(
        ["git", "tag"],
        cwd=".",
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    grep_proc = subprocess.Popen(
        [
            "grep",
            "-Eo",
            "[0-9]+\\.[0-9]+\\.[0-9]+"
        ],
        stdin=tag_proc.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    sort_proc = subprocess.Popen(
        ["sort"],
        stdin=grep_proc.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    tail_proc = subprocess.Popen(
        ["tail", "-1"],
        stdin=sort_proc.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    (stdout, _) = tail_proc.communicate()
    stdout = stdout.decode()
    return stdout.strip()


def enumerate_modules() -> list[str]:
    """
    Enumerate all additional modules that need to be included in the package.

    :return: The list of modules that should be included in the package
    """
    modules = []
    dotpy = ".py"
    for root_dir, _, files in os.walk("canopen"):
        for f in files:
            if f.endswith(dotpy):
                modules.append(
                    f"{root_dir.replace('/', '.')}.{f.replace(dotpy, '')}"
                )
    return modules


setup(
    name="canopen",
    version=get_version(),
    description="CANopen stack implementation",
    url="https://github.com/christiansandberg/canopen",
    author="Christian Sandberg",
    author_email="christiansandberg@me.com",
    license="MIT",
    py_modules=enumerate_modules(),
    install_requires=[],
)
