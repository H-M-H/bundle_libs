#!/usr/bin/env python3

import os
import re
import shutil
import subprocess

from collections import namedtuple

OTOOL_PATTERN = re.compile(r"(.+) \(.+\)")
RPATH_PATTERN = re.compile(r"^path (.+) \(.+\)")

EXCLUDE_LIB_PATHS = (
    '/usr/lib',
    '/System/Library/Frameworks/',
    )

Lib = namedtuple('Lib', ['req_bin', 'path', 'real_path'])


def otool(bin_path):
    """Yield all shared libraries directly referenced by the given binary."""
    p = subprocess.Popen(['otool', '-L', bin_path], stdout=subprocess.PIPE)
    # discard the first line, it just contains the binary name and no shared library
    p.stdout.readline()
    for l in p.stdout:
        m = re.match(OTOOL_PATTERN, str(l, encoding='utf-8').strip())
        if m:
            yield m.group(1)
    p.stdout.close()
    if p.wait() != 0:
        raise RuntimeError('otool failed with exitcode: {}'.format(p.returncode))


def otool_recursive(bin_path, exec_path=None, exclude_paths=None, lib_set=None):
    """
    Recursively yield all referenced shared libraries (also indirectly referenced).

    Yield namedtuples like (requesting_binary, relative_libpath, real_libpath).
    """

    if lib_set is None:
        lib_set = set()

    for b in otool(bin_path):
        lib = Lib(bin_path, b, real_path(b, bin_path=bin_path, exec_path=exec_path))
        if lib in lib_set:
            continue
        elif exclude_paths and b.startswith(exclude_paths):
            continue
        lib_set.add(lib)
        yield lib
        yield from otool_recursive(
            bin_path=lib.real_path,
            exec_path=exec_path,
            exclude_paths=exclude_paths,
            lib_set=lib_set
        )


def change_shared_lib(bin_path, old_path, new_path):
    """Adjust the searchpath of given shared library from old_path to new_path."""
    if subprocess.run([
            'install_name_tool',
            '-change',
            old_path,
            new_path,
            bin_path
    ]).returncode != 0:
        raise RuntimeError('Error: Changing path {} for {} failed.'.format(old_path, bin_path))


def set_shared_lib_id(lib, ID):
    """Set the id of a shared library."""
    if subprocess.run(['install_name_tool', '-id', ID, lib]).returncode != 0:
        raise RuntimeError('Error: Changing path id for {} failed.'.format(lib))


def rpaths(bin_path):
    """Yield rpaths of a given binary."""
    p = subprocess.Popen(['otool', '-l', bin_path], stdout=subprocess.PIPE)
    for line in p.stdout:
        if line == b'          cmd LC_RPATH\n':
            # skip line containing "cmdsize ..."
            p.stdout.readline()
            rpath_line = str(p.stdout.readline(), encoding='utf-8').strip()
            m = re.match(RPATH_PATTERN, rpath_line)
            if m:
                yield m.group(1)
            else:
                raise ValueError('Error: Could not extract rpath from: \'{}\''.format(rpath_line))


def add_rpath(bin_path, rpath):
    """Add rpath to binary."""
    if subprocess.run([
            'install_name_tool',
            '-add_rpath',
            rpath,
            bin_path
    ]).returncode != 0:
        raise RuntimeError('Error: Adding new rpath failed.')


def remove_rpaths(bin_path):
    """Remove all rpaths from given executable."""
    for r in rpaths(bin_path):
        if subprocess.run([
                'install_name_tool',
                '-delete_rpath',
                r,
                bin_path
        ]).returncode != 0:
            raise RuntimeError('Error: Removing rpath ({}) failed.'.format(r))


def real_path(path, bin_path=None, exec_path=None):
    """
    Return realpath.

    Resolve relative paths, (symbolic)links, @executable_path, @rpath and @loader_path according to
    bin_path and exec_path.
    """
    if exec_path is not None:
        epath = '@executable_path/'
        rpath = '@rpath/'

        if path.startswith(epath):
            exec_dir = os.path.dirname(exec_path)
            path = os.path.join(exec_dir, path[len(epath):])
            return real_path(path)
        elif path.startswith(rpath):
            path_rel = path[len(rpath):]
            for r in rpaths(exec_path):
                p = real_path(os.path.join(r, path_rel), bin_path=bin_path, exec_path=exec_path)
                if os.path.exists(p):
                    return p
            raise FileNotFoundError(path)

    if bin_path is not None:
        lpath = '@loader_path/'
        if path.startswith(lpath):
            loader_dir = os.path.dirname(bin_path)
            path = os.path.join(loader_dir, path[len(lpath):])
            return real_path(path)

    return os.path.realpath(path)


def main(): # noqa - only complexity is handling args
    """Execute mainprogram."""
    import argparse

    descr = (
        "This program will copy all shared libraries that are required for running the given "
        "executable (system libraries are excluded by default) to the specified directory and "
        "adjust the searchpaths to find these libraries. Note: Searchpaths are set relative to the "
        "executablepath, so the libraries can be deployed with the executable. Recursively all "
        "libraries required also indirectly will be retrieved. And accordingly the searchpaths of "
        "libraries crossreferencing other libraries will also be adjusted to use the deployed "
        "libraries."
    )

    parser = argparse.ArgumentParser(description=descr)
    parser.add_argument(
        'EXEC', type=str, help='Binary to adjust searchpaths and include shared libraries.'
    )
    parser.add_argument('--version', action='version', version='%(prog)s 1.0')
    parser.add_argument(
        '-l', '--list', action='store_true',
        help='Only list shared libraries, does not modify anything.'
    )
    parser.add_argument('-v', '--verbose', action='store_true', help='Be verbose.')
    parser.add_argument(
        '-x', '--exclude', type=str, nargs='*', default=EXCLUDE_LIB_PATHS,
        help='Exclude shared libraries starting with these paths. Default is \'{}\'.'.format(
            ' '.join(EXCLUDE_LIB_PATHS)
        )
    )
    parser.add_argument(
        '-L', '--lib-dir', type=str, default='../Libraries',
        help=(
            'Directory to install Libraries to relative to the given Binary. '
            'Defaults to: \'../Libraries\''
        )
    )
    parser.add_argument('-kr', '--keep-rpaths', action='store_true', help='Keep existing rpaths.')

    args = parser.parse_args()

    args.EXEC = os.path.realpath(args.EXEC)

    real_lib_dir = os.path.realpath(os.path.join(os.path.dirname(args.EXEC), args.lib_dir))

    path_set = set()
    if args.list:
        if args.verbose:
            print('requesting binary\trelative librarypath\treal librarypath')
        else:
            print('real librarypath')
        for l in otool_recursive(args.EXEC, exec_path=args.EXEC, exclude_paths=args.exclude):
            if args.verbose:
                print('{}\t{}\t{}'.format(*l))
            else:
                # print only paths we have not printed yet
                if l.real_path not in path_set:
                    path_set.add(l.real_path)
                    print(l.real_path)
    else:

        created_dir = False
        lib_set = set()
        for l in otool_recursive(
                args.EXEC, exec_path=args.EXEC, exclude_paths=args.exclude, lib_set=lib_set
        ):
            # copy libs only once
            if l.real_path not in path_set:
                if not created_dir:
                    # only create a directory if we actually want to copy something
                    os.makedirs(args.lib_dir, exist_ok=True)
                    created_dir = True

                path_set.add(l.real_path)
                if args.verbose:
                    print('Copying \'{}\' to \'{}\'.'.format(l.real_path, args.lib_dir))
                # for now lets assume that libraries will NOT have the same (base) name
                shutil.copy(l.real_path, args.lib_dir)

                lib_path_copy = os.path.join(real_lib_dir, os.path.basename(l.real_path))
                lib_path_rel_copy = os.path.join('@loader_path', os.path.basename(l.real_path))
                # also change the id/name of the shared lib
                set_shared_lib_id(lib_path_copy, lib_path_rel_copy)
                if args.verbose:
                    print('Setting id for shared lib \'{}\' to \'{}\'.'.format(
                        lib_path_copy, lib_path_rel_copy
                    ))

        for l in lib_set:
            # adjust the searchpaths for shared libraries

            # this contains the path to the copied library
            lib_path_copy = os.path.join(real_lib_dir, os.path.basename(l.real_path))

            if l.req_bin == args.EXEC:
                # in case we encounter the actual executable we want things relative to rpath
                lib_path_rel_copy = os.path.join('@rpath', os.path.basename(l.real_path))
                req_bin = l.req_bin
            else:
                # ... otherwise relative to loader_path (the directory containing the library)
                lib_path_rel_copy = os.path.join('@loader_path', os.path.basename(l.real_path))

                req_bin = os.path.join(real_lib_dir, os.path.basename(l.req_bin))

            if args.verbose:
                print(
                    'Changing searchpath for shared lib for binary '
                    '\'{}\' from \'{}\' to \'{}\''.format(req_bin, l.path, lib_path_rel_copy)
                )
            # finally adjust the searchpath
            change_shared_lib(req_bin, l.path, lib_path_rel_copy)

        if not args.keep_rpaths:
            if args.verbose:
                print('Removing old rpaths.')
            remove_rpaths(args.EXEC)

        rpath = '@executable_path/{}'.format(args.lib_dir)

        if args.verbose:
            print('Setting rpath(s) of \'{}\' to \'{}\'.'.format(args.EXEC, rpath))

        # add a resourcepath relative to the executable, so libraries can be loaded from the
        # specified lib-dir
        add_rpath(args.EXEC, rpath)


if __name__ == '__main__':
    main()
