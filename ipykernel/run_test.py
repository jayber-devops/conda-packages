import json
import os
import platform
import sys

py_major = sys.version_info[0]
py_impl = platform.python_implementation().lower()
machine = platform.machine().lower()

print("Python implementation:", py_impl)
print("              Machine:", machine)

specfile = os.path.join(
    os.environ["PREFIX"],
    "share",
    "jupyter",
    "kernels",
    "python{}".format(py_major),
    "kernel.json",
)

print("Checking Kernelspec at:     ", specfile, "...\n")

with open(specfile, "r") as fh:
    raw_spec = fh.read()

print(raw_spec)

spec = json.loads(raw_spec)

print("\nChecking python executable", spec["argv"][0], "...")

if spec["argv"][0].replace("\\", "/") != sys.executable.replace("\\", "/"):
    print(
        "The kernelspec seems to have the wrong prefix. \n"
        "Specfile: {}\n"
        "Expected: {}"
        "".format(spec["argv"][0], sys.executable)
    )
    sys.exit(1)