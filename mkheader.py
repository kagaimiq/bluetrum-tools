import argparse
import struct
from bluetrum.magic import *
from bluetrum.cipher import *
from bluetrum.crc import ab_crc16

###############################################################################

def anyint(s):
    return int(s, 0)

def hexstr(s):
    return bytes.fromhex(s)

ap = argparse.ArgumentParser(description='Generate the header.bin file (or a minimal boot image)')

ap.add_argument('-b', '--bootable', action='store_true',
                help='Generate a minimal bootable image instead of a partial header.bin file')

ap.add_argument('--load-addr', type=anyint, default=0x10800, metavar='ADDR',
                help='Load address (default: $%(default)04x)')

ap.add_argument('--entry-addr', type=anyint,  metavar='ADDR',
                help='Entry point (default is the same as load address)')

ap.add_argument('--offset', type=anyint, default=0x400, metavar='OFF',
                help='Offset where the code is being put in the image (default: $%(default)04x)')

ap.add_argument('--flags', type=anyint, default=0x0001,
                help='Flag bits to put inside the header (default: %(default)04X)\n'
                     '[bit0 = ?, bit2 = No CRC checks, bit3 = No scrambling]')

ap.add_argument('--chipid', type=hexstr, default=b'PRAO\x01\x00\x00\x00',
                help='Chip ID hex byte string (8-bytes) - default is for a [PRAO 1.0.0.0] chip.\n'
                     'bytes 0-3 = chip ID (PRAO, CRWN, etc.); bytes 4-7 = version? (e.g. 01 00 00 00)')

ap.add_argument('input',
                help='Input file')

ap.add_argument('output',
                help='Output file')

args = ap.parse_args()

###############################################################################

load_addr   = args.load_addr
entry_addr  = args.entry_addr
code_offset = args.offset

if entry_addr is None:
    entry_addr = load_addr

if code_offset < 0x200:
    print('Warning: the specified code offset is below a 512-byte mark. Adjusting.')
    code_offset = 0x200
elif code_offset & 0x1FF:
    print('Warning: the specified code offset is not a multiple of 512. Rounding up.')
    code_offset += 0x200 - (code_offset & 0x1FF)

scramb_data = (args.flags & 0x0008) == 0
have_crcs   = (args.flags & 0x0002) == 0

#---------------------------------------------

with open(args.input, 'rb') as f:
    code = f.read()

# pad code to the 4k boundary
code_end = code_offset + len(code)
code_end = (code_end + 0xfff) & ~0xfff
code += bytes(code_end - args.offset - len(code))

code_crc = ab_crc16(code)

print(f'Code offset: ${code_offset:04X}, size: {len(code)} bytes, CRC: ${code_crc:04X}')

# header magic
hmagic = struct.pack('<BH', 0x5A, args.flags)
hmagic += bytes([(0 - sum(hmagic)) & 0xff])

# assemble contents...
contents = bytearray(code_offset) + code

# make header
struct.pack_into('<4s8sIIII', contents, 0,
    hmagic, args.chipid,
    load_addr, entry_addr,
    code_offset, len(code))

if args.bootable:
    if not scramb_data:
        # well, we should at least have the first four bytes scrambled
        # where these flags live in...
        ab_lfsr_cipher_in(contents, 0, 4, MAGICKEY_LVMG)

    if have_crcs:
        # add CRCs
        struct.pack_into('<H', contents, 0x1c, code_crc)
        struct.pack_into('<H', contents, 0x3e, ab_crc16(contents[:0x3e]))
    elif scramb_data:
        # no place to store boot code CRC used for scrambling, blank it
        print('Asked to scramble the data while not requiring the CRCs to be populated - blanking the boot code CRC')
        code_crc = 0

    if scramb_data:
        # scramble header
        ab_lfsr_cipher_in(contents, 0, 64, MAGICKEY_LVMG)

        # scramble data
        for off in range(args.offset, len(contents), 512):
            ab_lfsr_cipher_in(contents,
                            off, min(512, len(contents) - off),
                            ((off >> 9) - 1) ^ MAGICKEY_LVMG ^ (code_crc * 0x00010001))
else:
    # just scramble the entire file
    ab_lfsr_cipher_in(contents, 0, len(contents), MAGICKEY_XFIL)

# write out
with open(args.output, 'wb') as f:
    f.write(contents)