from bluetrum.cipher import ab_calckey
from bluetrum.utils import *

import struct
import argparse

from base64 import b64decode
from tqdm import tqdm

###############################################################################

try:
    from serial import Serial
    from bluetrum.dl.uart import UARTDownload
    have_uart = True
except ImportError:
    have_uart = False

try:
    from scsiio import SCSIDev
    have_scsi = True
except ImportError:
    have_scsi = False

if not have_uart and not have_scsi:
    print('No available ways of communcating with hardware.')
    print('Install pyserial for UART or rip "scsiio" from jl-uboot-tool for USB MSC.')
    exit(1)

###############################################################################

ap = argparse.ArgumentParser(description='Enter the bluetrum download mode and get basic info from the chip')

if have_uart:
    ap.add_argument('--init-baud', type=int, default=115200,
                    help='Initial baudrate (default: %(default)d baud)')
    ap.add_argument('--baud', type=int, default=921600,
                    help='Baudrate to use (default: %(default)d baud)')
    ap.add_argument('--port',
                    help='Serial port to use for UART bootloader')

if have_scsi:
    ap.add_argument('--mscdev',
                    help='USB MSC (SCSI) device to use for USB bootloader')

ap.add_argument('-r', '--reboot', action='store_true',
                help='Reboot the chip after completion')

actsp = ap.add_subparsers(dest='action')

asp_erase = actsp.add_parser('erase', help='Erase one or more flash areas')
asp_erase.add_argument('areas', metavar='address size', nargs='+',
                       help='Erase <size> bytes at <address> - note: this will be aligned to an eraseblock boundary.'
                            ' If <size> is 0, then it\'s assumed to be \'whole flash\'.')

asp_read = actsp.add_parser('read', help='Read the flash into the file')
asp_read.add_argument('areas', metavar='address size file', nargs='+',
                      help='Read <size> bytes from <address> into <file>.'
                           ' If <size> is 0, then it\'s assumed to be \'whole flash\'.')

asp_write = actsp.add_parser('write', help='Write the file into flash')
asp_write.add_argument('areas', metavar='address file', nargs='+',
                       help='Write <file> starting at <address>')

args = ap.parse_args()

###############################################################################

desblob = b64decode(
    "bwAACP////////////////////////////////////////////////////////////////////"
    "//////////////////////////////////////////////////////////////////////////"
    "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"
)




def make_cb(cmd, arg1=0, arg2=0, arg3=0):
    # just the unscrambled CB is fine for now
    return struct.pack('>BIBH', cmd, arg1, arg2, arg3)

def do_the_stuff(execcmd, blocksize, iface):
    # Query the information
    resp = execcmd(make_cb(0x5A, arg1=0x5259414E, arg3=0x67ca), recv=24)
    chipid, loadaddr, commskey, _ = struct.unpack('>12sIII', resp)
    print(f' Chip ID:       {chipid}')
    print(f' Load address:  ${loadaddr:08X}')
    print(f' Init. commkey: ${commskey:08X}')

    # Authorize
    resp = execcmd(make_cb(0x55, arg1=ab_calckey(commskey)), recv=4)
    commskey, = struct.unpack('>I', resp)
    print(f' New commkey:   ${commskey:08X}')

    # Change baudrate (if it's UART)
    if iface == 'uart' and args.baud != args.init_baud:
        print(f'Changing baudrate to {args.baud} baud...')
        resp = execcmd(make_cb(0x50, arg1=args.baud, arg2=2), recv=2, switch_baud=args.baud)
        print('response:', resp.hex())

    # Load blob
    data = bytearray(desblob) + b'\x00' * align_by(len(desblob), blocksize)
    struct.pack_into('<12s4sI', data, 4,
                     chipid, iface.encode(), blocksize)

    execcmd(make_cb(0x57, arg1=loadaddr, arg3=(len(data) // blocksize)), send=data)
    execcmd(make_cb(0x58, arg1=loadaddr))

    # start!
    btitle, codekey, flashid = struct.unpack('<16sI12s', execcmd(make_cb(0x00), recv=32))
    print('- Title:', btitle)
    print(f'- Code key: >>>>{codekey:08X}<<<<')
    print('- Flash ID:', flashid.hex(' '), '...')

    # quick and dirty way of determining the flash size from its ID
    density = flashid[2]
    if density >= 0x10 and density <= 0x18:
        fsize = 1 << density
        print(f'  - Flash size: {fsize} bytes')
    else:
        fsize = None
        print('  - Could not determine flash size')



    def do_dev_erase(addr, size):
        saddr = addr & ~0xFFF
        eaddr = (addr + size + 0xFFF) & ~0xFFF

        if saddr < addr:
            print(f'Warning: start address has been adjusted: ${saddr:06X} < ${addr:06X}')
        if eaddr > (addr+size):
            print(f'Warning: end address has been adjusted: ${eaddr:06X} > ${addr+size:06X}')

        tq = tqdm(desc='Erasing', total=(eaddr-saddr), unit='B', unit_divisor=1024, unit_scale=1)

        try:
            addr = saddr
            while addr < eaddr:
                if (eaddr-saddr) >= 0x10000 and (addr & 0xFFFF) == 0:
                    # big eraseblock (64k)
                    blksize = 0x10000
                    flags = 0x00
                else:
                    # small eraseblock (4k)
                    blksize = 0x1000
                    flags = 0x02

                execcmd(make_cb(0x03, arg1=addr, arg2=flags))

                tq.update(blksize)
                addr += blksize

        finally:
            tq.close()


    # let's do stuff now!
    try:
        if args.action == 'erase':
            for i in range(0, len(args.areas), 2):
                addr = int(args.areas[i+0], 0)
                size = int(args.areas[i+1], 0)

                if size <= 0:
                    if fsize is None:
                        raise RuntimeError('Could not determine the device size because there is no info about it')
                    size = fsize - addr
                    if size <= 0:
                        raise ValueError('Address is out of range')

                do_dev_erase(addr, size)

        elif args.action == 'read':
            for i in range(0, len(args.areas), 3):
                addr = int(args.areas[i+0], 0)
                size = int(args.areas[i+1], 0)
                path = args.areas[i+2]

                if size <= 0:
                    if fsize is None:
                        raise RuntimeError('Could not determine the device size because there is no info about it')
                    size = fsize - addr
                    if size <= 0:
                        raise ValueError('Address is out of range')

                io_size = min(0x8000, max(blocksize, align_to(size // 100, blocksize)))

                print(f'Reading {size} bytes from @{addr:06X} into "{path}"...')

                tq = tqdm(desc='Reading', total=size, unit='B', unit_divisor=1024, unit_scale=True)

                try:
                    with open(path, 'wb') as f:
                        done = 0
                        while done < size:
                            n = min(io_size, size-done)

                            f.write(execcmd(make_cb(0x01, arg1=addr+done, arg3=n), recv=n))

                            tq.update(n)
                            done += n

                finally:
                    tq.close()

        elif args.action == 'write':
            for i in range(0, len(args.areas), 2):
                addr = int(args.areas[i+0], 0)
                path = args.areas[i+1]

                with open(path, 'rb') as f:
                    size = f.seek(0, 2)
                    f.seek(0)

                    print(f'Writing {size} bytes to @{addr:06X} from "{path}"...')

                    # Erase
                    do_dev_erase(addr, size)

                    # Write
                    io_size = min(0x8000, max(blocksize, align_to(size // 100, blocksize)))

                    tq = tqdm(desc='Writing', total=size, unit='B', unit_divisor=1024, unit_scale=True)

                    try:
                        with open(path, 'rb') as f:
                            done = 0
                            while done < size:
                                block = f.read(io_size)

                                execcmd(make_cb(0x02, arg1=addr+done, arg3=len(block)), send=block)

                                tq.update(len(block))
                                done += len(block)

                    finally:
                        tq.close()

    except Exception as e:
        print('failed:', e)

    except KeyboardInterrupt:
        print('interrupted!')

    if args.reboot:
        # finally, reboot the chip
        execcmd(make_cb(0x5E))

###############################################################################

if args.port is not None:
    with Serial(args.port) as port:
        udl = UARTDownload(port)

        print('Trying to synchronize', end='')

        port.timeout = .01

        try:
            done = False
            i = 0
            while not done:
                if (i % 10) == 0:
                    print('.', flush=True, end='')

                    if (i % 20) == 0:
                        # first try with the target baudrate - maybe the chip is already in?
                        udl.port.baudrate = args.baud
                    elif (i % 20) == 10:
                        # then try with the initial baudrate.
                        udl.port.baudrate = args.init_baud

                    udl.send_reset(True)

                udl.port.reset_input_buffer()

                # send a sync pattern
                udl.port.write(UARTDownload.SYNC_TOKEN)
                while not done:
                    recv = udl.port.read(4)
                    if recv == b'': break
                    if recv == UARTDownload.SYNC_RESP:
                        done = True

                i += 1

        finally:
            print()

        print('Got it!')

        port.timeout = .05

        def execcmd(cb, send=None, recv=None, max_io=512, switch_baud=None):
            # first goes the command block
            udl.send_packet(cb)

            # switch baudrate at that point
            if switch_baud is not None:
                port.baudrate = switch_baud

            # transfer data
            if send is not None:
                # send data blocks
                done = 0
                while done < len(send):
                    rem = len(send) - done
                    n = min(max_io, rem)

                    udl.send_packet(send[done : done+n])
                    done += n

            elif recv is not None:
                # receive data blocks
                data = b''
                while len(data) < recv:
                    rem = recv - len(data)
                    n = min(max_io, rem)

                    block = udl.recv_packet()
                    data += block

                    if len(block) != n:
                        break

                return data

        do_the_stuff(execcmd, 512, 'uart')

elif args.mscdev is not None:
    with SCSIDev(args.mscdev) as dev:
        def execcmd(cb, send=None, recv=None):
            if recv is not None:
                recv = bytearray(recv)

            if send is not None and not isinstance(send, bytes):
                send = bytes(send)

            dev.execute(b'\xfc' + cb, send, recv)

            return recv

        do_the_stuff(execcmd, 512, 'usb')

else:
    print('No device specified:')
    if have_uart: print(' - UART: specify the serial port via the "--port" option')
    if have_scsi: print(' - USB MSC: specify the device via the "--mscdev" option')
