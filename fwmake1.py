from bluetrum.cipher import *
from bluetrum.crc import *
from bluetrum.magic import *
from bluetrum.utils import *

import struct
import argparse
from pathlib import Path

###############################################################################

ap = argparse.ArgumentParser(description='Bluetrum Firmware Maker 1.0')

ap.add_argument('-u', '--userkey', type=anyint,
                help='The "user key" (term may change in the future) to use for scrambling the code area'
                     ' (by default none is applied, code is scrambled using the generic way.)')

ap.add_argument('--no-res-scramble', action='store_false', dest='scramble_res',
                help='Do not scramble the resource region data')

ap.add_argument('output', type=Path,
                help='The output file')

ap.add_argument('header', type=Path,
                help='The "header.bin" file that contains the boot code and some bits of the header')

ap.add_argument('appbin', type=Path,
                help='The "app.bin" file that contains the main code')

ap.add_argument('resbin', type=Path, nargs='?',
                help='The "res.bin" file that contains the resources of the firmware.')

args = ap.parse_args()

###############################################################################

#
# Code scrambling key
#
codekey = 0
if args.userkey is not None:
    codekey = ab_calcuserkey(args.userkey)
    print(f'Using the key ${codekey:08x} (obtained from ${args.userkey:08x})')

#
# Load the header.bin file
#
with open(args.header, 'rb') as f:
    header = ab_lfsr_cipher(f.read(), MAGICKEY_XFIL)

    hmagic, hchipid, bootload, bootentry, bootoffset, bootsize = struct.unpack_from('<4s8sIIII', header, 0)

    if hmagic[0] != 0x5A or (sum(hmagic) & 0xFF) != 0x00:
        print(f'Invalid header file supplied! (magic bytes are {hmagic.hex()})')
        exit(2)

    hflags = int.from_bytes(hmagic[1:2], 'little')

    hflag_scramble = (hflags & 0x0008) == 0
    hflag_nocrcs   = (hflags & 0x0002) != 0

    print('** Header info **')
    print(f'Header magic:           {hmagic.hex()}')
    print(f'   ... flags:           ${hflags:04X} - b3:scramble? {hflag_scramble}, b1:no crcs? {hflag_nocrcs}')
    print(f'Header chip ID:         {hchipid}')
    print(f'Boot code load address: ${bootload:08X}')
    print(f'Boot code entry point:  ${bootentry:08X}')
    print(f'Boot code offset:       ${bootoffset:08X}')
    print(f'Boot code size:         ${bootsize:08X} ({bootsize} bytes)')

    if bootoffset > len(header):
        print(f'** Boot code offset (${bootoffset:08X}) is beyond the header file size')
        exit(2)

    if bootoffset + bootsize > len(header):
        print(f'** Boot code is bigger than what the header file actually has ({bootsize} > {len(header) - bootoffset})')
        exit(2)

    bootcrc = ab_crc16(header[bootoffset : bootoffset+bootsize])

    print(f'Boot code CRC16:        ${bootcrc:04X}')

    print()

#
# Load app.bin and res.bin
#
regions = []

with open(args.appbin, 'rb') as f:
    regions.append((MAGICSIGN_XCOD, f.read(), codekey ^ (0x00010001 * bootcrc) ^ MAGICKEY_XAPP))

if args.resbin is not None:
    with open(args.resbin, 'rb') as f:
        regions.append((MAGICSIGN_XRES, f.read(), 0 if args.scramble_res else None))

#
# Start building the contents
#

contents = bytearray(header)
contents += b'\xff' * align_by(len(contents), 0x2000)

#
# Prepare the boot header contents
#

if not hflag_scramble:
    # In case when header flags state to not scramble the boot header, we shall at least
    # scramble the first four magic bytes (that are checked as if they were scrambled).
    ab_lfsr_cipher_in(contents, 0, 4, MAGICKEY_LVMG)

# put the CRC's (who cares if the flags tell otherwise)
struct.pack_into('<H', contents, 0x1C, bootcrc)
struct.pack_into('<H', contents, 0x3E, ab_crc16(contents[:0x3E]))

if hflag_scramble:
    # scramble the whole boot header
    ab_lfsr_cipher_in(contents, 0, 0x40, MAGICKEY_LVMG)

    # and the boot code
    for off in range(bootoffset, bootoffset+bootsize, 512):
        key = MAGICKEY_LVMG ^ (0x00010001 * bootcrc) ^ ((off >> 9) - 1)
        ab_lfsr_cipher_in(contents, off, 512, key)

#
# Put the app/res regions
#

# this looks horrible, but at least
# it yields a byte-exact output.
for i, (rmagic, rdata, rkey) in enumerate(regions):
    # pad to a block boundary
    rdata += bytes(align_by(len(rdata), 512))

    # region header
    regoff = len(contents)
    contents += bytes(align_to(16 + 2*(len(rdata)//512), 512))
    # region data
    dataoff = len(contents)
    contents += rdata
    # additional padding
    if (i+1) == len(regions):
        contents += bytes(align_by(len(contents), 4096))

    # fill in region table entry
    struct.pack_into('<IIIHBB', contents, 0x40 + 0x10*i,
        regoff, len(rdata), 0, ab_crc16(contents[dataoff:]), i, rkey is not None
    )

    # fill in region header
    struct.pack_into('<4sIIH', contents, regoff,
        rmagic, dataoff-regoff, len(rdata), 16
    )
    struct.pack_into('<H', contents, regoff+14,
        ab_crc16(contents[regoff : regoff+14])
    )
    for coff in range(regoff+16, dataoff, 2):
        blki = (coff - regoff - 16) // 2
        rboff = blki * 512
        boff = rboff + dataoff

        if rboff < len(rdata):
            # CRC of the block
            crc = ab_crc16(contents[boff : boff+512], blki + 1)
        else:
            # Fill the rest to obscure the gap (I'm doing that just to have byte-exact output)
            crc = ab_crc16(contents[regoff : coff], coff)

        struct.pack_into('<H', contents, coff, crc)

    # scramble blocks, if neccessary
    if rkey is not None:
        for boff in range(dataoff, len(contents), 512):
            blki = (boff - dataoff) // 512
            crc, = struct.unpack_from('<H', contents, regoff + 16 + blki*2)
            ab_lfsr_cipher_in(contents, boff, 512, rkey ^ crc)

    print(f'{rmagic.hex()} -- @{regoff:08X} / {len(rdata)} bytes')

#
# Finalize the region table
#
rtcrc = ab_crc16(contents[0x40:0x80])
struct.pack_into('<H', contents, 0x80, rtcrc)
ab_lfsr_cipher_in(contents, 0x40, 0x40, MAGICKEY_XAPP ^ (rtcrc * 0x00010001))

#
# Write the resulting image out
#
with open(args.output, 'wb') as f:
    f.write(contents)
