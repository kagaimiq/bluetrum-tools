from bluetrum.utils import *
from bluetrum.magic import MAGICSIGN_ENTR

import argparse
import struct

from pathlib import Path

##################################################

ap = argparse.ArgumentParser(description='Make a bluetrum resource blob file')

ap.add_argument('--align', type=anyint, default=32,
                help='Align each file entry to the specified alignment')

ap.add_argument('--base', type=anyint, default=0x11000000,
                help='Resource area base address (default: 0x%(default)x)')

ap.add_argument('input', type=Path,
                help='Input resource directory or resource layout file.')

ap.add_argument('output', type=Path,
                help='Output resource file path')

args = ap.parse_args()

##################################################

def parse_orderfile(files, fpath):
    with open(fpath, 'r') as f:
        while True:
            ln = f.readline()
            if ln == '': break

            # strip comments
            pos = ln.find('//')
            if pos >= 0: ln = ln[:pos]

            # an override operator
            pos = ln.find('->')
            if pos >= 0:
                ename = ln[:pos].strip()
                spath = ln[pos+2:].strip()
                if spath == '':
                    # empty override
                    spath = None
                else:
                    spath = Path(spath)
            else:
                ename = ln.strip()
                spath = None

            # empty entry name or just an empty line - ignore
            if ename == '': continue

            files[ename] = spath


def scan_dir(files, dpath, prefix=''):
    for fpath in dpath.iterdir():
        if fpath.is_dir():
            scan_dir(files, fpath, f'{prefix}{fpath.name}_')

        else:
            fname = prefix + fpath.name

            if fname in files and files[fname] is not None:
                print(f'File "{fname}" already exists!')
                continue

            files[fname] = fpath

#--------------------------------------------------------

files = {}

if args.input.is_dir():
    scan_dir(files, args.input)
else:
    parse_orderfile(files, args.input)

    # manually assign the file paths
    for ename in files:
        if files[ename] is None:
            fpath = args.input / ename
            if args.input.exists():
                # if the file does actually exist
                files[ename] = fpath

#--------------------------------------------------------

data = bytearray(32 + len(files) * 32)
struct.pack_into('<4s24sI', data, 0, MAGICSIGN_ENTR, b'', len(files))

for i, ename in enumerate(files):
    # get the data
    fpath = files[ename]
    if fpath is not None:
        # read the file data
        fdata = fpath.read_bytes()
    else:
        # empty file data
        fdata = b''

    # encode the file name
    bename = ename.encode()
    if len(bename) >= 24:
        print(f'Name "{ename}" is too long ({len(bename)} bytes), truncating..')
        bename = bename[:23]

    # add the alignment padding
    data += bytes(align_by(len(data), args.align))

    address = args.base + len(data)

    print(f'[{i}]: @{address:X} ({len(fdata)}) - "{ename}"')

    # populate the file entry info
    struct.pack_into('<24sII', data, 32 + i*32,
                        bename, address, len(fdata))

    # append the data
    data += fdata

args.output.write_bytes(data)
