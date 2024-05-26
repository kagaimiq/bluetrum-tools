import argparse, struct
from pathlib import Path
from bluetrum.cipher import *
from bluetrum.crc import *
from bluetrum.magic import *

################################################################################

ap = argparse.ArgumentParser(description='Unpack a Bluetrum flash/firmware image')

def anyint(s):
    return int(s, 0)

ap.add_argument('-u', '--userkey', metavar='KEY', type=anyint,
                help='User key which is used to encrypt the main application blob')

ap.add_argument('file', nargs='+',
                help='Firmware file(s) to parse')

args = ap.parse_args()

################################################################################

def parse_res(data, outdir, base=0x11000000):
    magic, hwtw, entcnt = struct.unpack_from('<4s24sI', data, 0)

    if magic != b'\xC5\xCE\xD4\xD2':   # 'ENTR' with MSBs set
        print('Res header magic mismatch')
        return

    if 32 + entcnt * 32 >= len(data):
        print('Entries go over the res region!')
        return

    outdir.mkdir(exist_ok=True)

    entries = []

    for i in range(entcnt):
        ename, eaddr, esize = struct.unpack_from('<24sII', data, 32 + i * 32)

        # address sanity check no.1
        if eaddr < base:
            print(f'Entry #{i} base address (%{eaddr:x}) goes under the map base (%{base:x})')
            break

        eoff = eaddr - base

        # address sanity check no. 2
        if eoff + esize > len(data):
            print(f'Entry #{i} goes over the region by {eoff + esize - len(data)} bytes')
            break

        # null-terminated filename
        zeroidx = ename.find(b'\0')
        if zeroidx < 0: zeroidx = len(ename)
        ename = ename[:zeroidx].decode()

        print(f'#{i} [{ename:24s}] @{eoff:08x}, {esize} bytes')

        # just in case
        if len(ename) == 0:
            print(f'Entry #{i} has no name')
            continue

        entries.append((ename, eoff, esize))

    for ename, eoff, esize in entries:
        if esize == 0:  # if it's feasible
            continue

        # dump it to file
        (outdir/ename).write_bytes(data[eoff : eoff+esize])

    # make an entry order file too
    with open(outdir/'00__order__00.txt', 'w') as f:
        f.write("""\
// NOTICE: You should not modify the order of the resource files below in any way.
// The firmware refers to each resource by the means of hardcoded offsets to the
// address and size fields of the entries themselve, meaning that if you change
// the order of the items (or insert something in between), you'll most likely just break it.
// This file solely exists to not alter the order of the entries in case the filesystem where
// these entries are being extracted to alters the order even further.
// Also, the entries that are zero bytes in length are also listed there,
// instead of being extracted like any other file.

"""
        )

        for ename, eoff, esize in entries:
            f.write(f'{ename}\n')

        f.write('\n// Here is the end.\n')

#---------------------------------------------------------------#

def parse_flash_image(data, outdir, userkey=0):
    data = bytearray(data)
    outdir.mkdir(exist_ok=True)

    #
    # Parse the header
    #
    ab_lfsr_cipher_in(data, 0, 0x40, MAGICKEY_LVMG)

    # Check the header CRC
    hdr, hcrc = struct.unpack_from('<62sH', data, 0x00)
    if ab_crc16(hdr) != hcrc:
        print('Header CRC mismatch')

    # Decompose the header
    hmagic, chipid, bootload, bootentry, bootoff, bootsz, bootcrc, h1rem = struct.unpack('<4s8sIIIIH32s', hdr)

    if hmagic[0] != 0x5A or (sum(hmagic) & 0xFF) != 0x00:
        print(f'Header magic is invalid!')
        return

    print(f'Header magic -- {hmagic.hex()}')
    print(f'Chip ID: -- {chipid}')
    print(f'Bootloader: load @{bootload:x}, entry @{bootentry:x} - offset @{bootoff:x}, {bootsz} bytes long - CRC {bootcrc:04x}')
    print('Header remaining stuff:', h1rem.hex())

    #
    # Decrypt the boot code
    #
    for off in range(bootoff, bootoff + bootsz, 512):
        key = MAGICKEY_LVMG ^ (0x00010001 * bootcrc) ^ ((off >> 9) - 1)
        ab_lfsr_cipher_in(data, off, 512, key)

    bootcode = data[bootoff:bootoff+bootsz]

    # Check the boot code CRC
    if ab_crc16(bootcode) != bootcrc:
        print('Boot code CRC mismatch')

    # Dump the boot code into a file
    (outdir/'boot-code.bin').write_bytes(bootcode)

    # Make a header.bin file from the portions of header data (that is, bare minimum main header contents and the boot code itself)
    with open(outdir/'header.bin', 'wb') as f:
        hdrbin = bytearray(bootoff) + bootcode
        struct.pack_into('<4s8sIIII', hdrbin, 0, hmagic, chipid, bootload, bootentry, bootoff, bootsz)
        f.write(ab_lfsr_cipher(hdrbin, MAGICKEY_XFIL))


    #
    # Parse the region table
    #
    rtcrc, = struct.unpack_from('<H', data, 0x80)

    ab_lfsr_cipher_in(data, 0x40, 0x40, MAGICKEY_XAPP ^ (0x00010001 * rtcrc))

    if ab_crc16(data[0x40:0x80]) != rtcrc:
        print('Region table CRC error')

    regions = []

    for off in range(0x40, 0x60, 0x10):
        # offset, size, what, CRC16, what, what
        regions.append(struct.unpack_from('<IIIHBB', data, off))

    #
    # Parse the regions themselves
    #
    for ri, (roffset, rsize, rwhat1, rcrc, rwhat2, rwhat3) in enumerate(regions):
        print(f'region {ri} :: @{roffset:x} ({rsize} bytes) | {rwhat1} | CRC {rcrc:04x} | {rwhat2}/{rwhat3}')

        if rwhat2 == 0:
            # the main app region uses the special key
            key = MAGICKEY_XAPP ^ (0x00010001 * bootcrc) ^ userkey
        else:
            # everything else (e.g. resources) do not
            key = 0

        #
        # Read the region header
        #
        rh_hdr, rh_hcrc = struct.unpack_from('<14sH', data, roffset)
        if ab_crc16(rh_hdr) != rh_hcrc:
            print('Region header CRC mismatch')
            continue

        rh_type, rh_hsize, rh_dsize, rh_wtw = struct.unpack_from('<4sIIH', data, roffset)

        rh_type = bytes([v & 0x7F for v in rh_type]).decode()   # TODO: something more reliable? (if it ever fails)
        dataoff = roffset + rh_hsize

        print(f'-> "{rh_type}" - header @{roffset:x} ({rh_hsize} bytes), data @{dataoff:x} ({rh_dsize} bytes), wtw = {rh_wtw:04x}')

        # XXX
        if rh_dsize != rsize:
            print('Region data sizes mismatch')
            continue

        ## FIXME - is that correct?
        #
        # It's either the resources region or the last region (most likely)
        # that actually spans over to the last 4k block boundary (despite the headers claiming less)
        # - and the CRC field in the region entry actually includes this as well!
        #   .. well maybe just padding with zeroes will make the thing go but the scrambling also goes this far!
        #
        if (ri+1) == len(regions):
            # this should be aligned to a 4k boundary!
            dataend = (dataoff + rh_dsize + 0xfff) & ~0xfff
        else:
            # align to a 512-byte boundary
            dataend = (dataoff + rh_dsize + 0x1ff) & ~0x1ff

        print(f'  data spans :: @{dataoff:x}...{dataend-1:x}')

        #
        # Deobfuscate the data!
        #
        for off in range(dataoff, dataend, 512):
            reloff = off - dataoff
            block = reloff // 512

            # the space between the header and the data is the CRCs of the blocks!!
            blockcrc, = struct.unpack_from('<H', data, roffset + 16 + block * 2)

            # here we go!
            ab_lfsr_cipher_in(data, off, 512, key ^ blockcrc)

            # check the block CRC real quick
            if ab_crc16(data[off:off+512], block + 1) != blockcrc and reloff < rh_dsize:
                print(f'Block CRC error ({reloff:x} / {blockcrc:04X})')
                break

        # Another CRC check
        if ab_crc16(data[dataoff : dataend]) != rcrc:
            print('Region data CRC mismatch')
            if rh_type == 'XCOD':
                print("** That was the main code area. Perhaps you haven't supplied a correct userkey?")
                break
            continue

        regdata = data[dataoff : dataoff + rh_dsize]

        # Actually dealing with the data
        if rh_type == 'XCOD':
            # The Code
            (outdir/'app.bin').write_bytes(regdata)
        elif rh_type == 'XRES':
            # The Resources
            (outdir/'res.bin').write_bytes(regdata)
            parse_res(regdata, outdir/'res')
        else:
            # Something else
            (outdir/f'region_{rh_type}.bin').write_bytes(regdata)

    #
    # Save the decrypted image
    #
    (outdir/'decrypted.bin').write_bytes(data)


################################################################################

if args.userkey is not None:
    userkey = ab_calcuserkey(args.userkey)
    print(f'Using userkey {args.userkey:08x} {userkey:08x}')
else:
    userkey = 0
    print('No userkey specified')


for fname in args.file:
    print(f'\n#\n# {fname}\n#\n')

    try:
        outdir = Path(fname + '_unpack')

        with open(fname, 'rb') as f:
            hdr = f.read(4) ; f.seek(0)
            if hdr == b'DCF\0':
                raise NotImplementedError('DCF parsing is not implemented yet')
            else:
                data = bytearray(f.read())
                parse_flash_image(data, outdir, userkey)

    except Exception as e:
        print('[!]', e)
