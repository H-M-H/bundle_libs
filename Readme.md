## bundle_libs.py - deploy dynamic libraries on macOS

This script is intended to make deploying programs on macOS that require additional dynamic
libraries easier. Basically it copies all required libraries to a specified location and fixes
the corresponding searchpaths stored in the executable as well as in the copied libraries.

### Installation

bundle_libs.py is written in Python and requires at least Python 3.5.
To run it just download the bundle_libs.py file and mark it as executable with:
`chmod +x bundle_libs.py`. Then `./bundle_libs.py program_to_deploy` is sufficient to run it.

### Usage:

```
usage: bundle_libs.py [-h] [--version] [-l] [-v] [-x [EXCLUDE [EXCLUDE ...]]]
                      [-L LIB_DIR] [-kr]
                      EXEC

This program will copy all shared libraries that are required for running the
given executable (system libraries are excluded by default) to the specified
directory and adjust the searchpaths to find these libraries. Note:
Searchpaths are set relative to the executablepath, so the libraries can be
deployed with the executable. Recursively all libraries required also
indirectly will be retrieved. And accordingly the searchpaths of libraries
crossreferencing other libraries will also be adjusted to use the deployed
libraries.

positional arguments:
  EXEC                  Binary to adjust searchpaths and include shared
                        libraries.

optional arguments:
  -h, --help            show this help message and exit
  --version             show program's version number and exit
  -l, --list            Only list shared libraries, does not modify anything.
  -v, --verbose         Be verbose.
  -x [EXCLUDE [EXCLUDE ...]], --exclude [EXCLUDE [EXCLUDE ...]]
                        Exclude shared libraries starting with these paths.
                        Default is '/usr/lib /System/Library/Frameworks/'.
  -L LIB_DIR, --lib-dir LIB_DIR
                        Directory to install Libraries to relative to the
                        given Binary. Defaults to: '../Libraries'
  -kr, --keep-rpaths    Keep existing rpaths.
```

### How does it work ?

macOS provides two command line tools to observe and change searchpaths for dynamic/shared
libraries, namely these are: `otool` and `install_name_tool`. These tools are called several times
via Pythons subprocess module inorder to accomplish the more complex process of deploying all
required libraries.

### License

CC0, see LICENSE

### Credits

This project is maintained by @H-M-H
