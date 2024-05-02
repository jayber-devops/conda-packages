Currently this package injects `python.exe` into the kernel.json spec file.
It is likely that this has been addressed in newer versions, but should be
tested before rebuilding, the current build on `esri` has this behavior 
manually patched. If it persists, we can use the fix_kernelspec.py script
to modify it, just having the first value as `python` seems to work.
