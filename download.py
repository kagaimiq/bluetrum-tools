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
    print('No available ways to communicate with the hardware.')
    print('Install pyserial for UART or rip "scsiio" from jl-uboot-tool for USB MSC.')
    exit(1)

###############################################################################

ap = argparse.ArgumentParser(description='Tool to communicate with the bootloader in the Bluetrum chips.')

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

dl_blob = b64decode(
    "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"
)

#------------------------------------------------------------------------------

class BlCmd:
    IFACE_PARAM         = 0x50
    MEM_READ            = 0x52
    AUTHORIZE           = 0x55
    MEM_WRITE           = 0x57
    SET_CMD_HANDLER     = 0x58
    GET_INFO            = 0x5A
    REBOOT              = 0x5E

class NitDlCmd:
    INIT                = 0x00
    DEV_READ            = 0x01
    DEV_WRITE           = 0x02
    DEV_ERASE           = 0x03



def make_cb(cmd, arg1=0, arg2=0, arg3=0):
    # just the unscrambled CB is fine for now
    return struct.pack('>BIBH', cmd, arg1, arg2, arg3)

def do_the_stuff(execcmd, blocksize, iface):
    # Query the information
    resp = execcmd(make_cb(BlCmd.GET_INFO, arg1=0x5259414E, arg3=0x67ca), recv=24)
    chipid, loadaddr, commskey, _ = struct.unpack('>12sIII', resp)
    print(f' Chip ID:       {chipid}')
    print(f' Load address:  ${loadaddr:08X}')
    print(f' Init. commkey: ${commskey:08X}')

    # Authorize
    resp = execcmd(make_cb(BlCmd.AUTHORIZE, arg1=ab_calckey(commskey)), recv=4)
    commskey, = struct.unpack('>I', resp)
    print(f' New commkey:   ${commskey:08X}')

    # Change baudrate (if it's UART)
    if iface == 'uart' and args.baud != args.init_baud:
        print(f'Changing baudrate to {args.baud} baud...')
        # switch to a faster clock reference
        execcmd(make_cb(BlCmd.IFACE_PARAM, arg2=0xf0), recv=2)
        # change the baud rate
        execcmd(make_cb(BlCmd.IFACE_PARAM, arg1=args.baud, arg2=0x02), recv=2, switch_baud=args.baud)

    # Load blob
    data = bytearray(dl_blob) + b'\x00' * align_by(len(dl_blob), blocksize)
    struct.pack_into('<12s4sI', data, 4,
                     chipid, iface.encode(), blocksize)

    execcmd(make_cb(BlCmd.MEM_WRITE, arg1=loadaddr, arg3=(len(data) // blocksize)),send=data)
    execcmd(make_cb(BlCmd.SET_CMD_HANDLER, arg1=loadaddr))

    # start!
    codekey, flashid, flashuid = struct.unpack('II16s', execcmd(make_cb(NitDlCmd.INIT), recv=48))
    print(f'- Code key: >>>> {codekey:08X} <<<<')
    print(f'- Flash device ID: {flashid:06X}')
    print(f'- Flash unique ID: {flashuid.hex()}')

    # quick and dirty way of determining the flash size from its ID
    density = flashid & 0xff
    if density >= 0x10 and density <= 0x18:
        fsize = 1 << density
        print(f'- Flash size: {fsize} bytes')
    else:
        fsize = None
        print(' - Unknown flash size')

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
                if (eaddr-addr) >= 0x10000 and (addr & 0xFFFF) == 0:
                    # big eraseblock (64k)
                    blksize = 0x10000
                    flags = 0x00
                else:
                    # small eraseblock (4k)
                    blksize = 0x1000
                    flags = 0x02

                execcmd(make_cb(NitDlCmd.DEV_ERASE, arg1=addr, arg2=flags))

                tq.update(blksize)
                addr += blksize

        finally:
            tq.close()

    #--------------------------------------------------

    try:
        if args.action == 'erase':
            for i in range(0, len(args.areas), 2):
                addr = int(args.areas[i+0], 0)
                size = int(args.areas[i+1], 0)

                if size <= 0:
                    if fsize is None:
                        raise RuntimeError('Unknown flash size')
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
                        raise RuntimeError('Unknown flash size')
                    size = fsize - addr
                    if size <= 0:
                        raise ValueError('Address is out of range')

                # we wouldn't have needed that if we just supported the UART bootloader
                # and simply updated the progress on each transferred block, but since
                # we need to support the USB bootloader as well, there is no possibility
                # to the same thing except by doing short bursts at a time.
                io_size = min(0x8000, max(blocksize, align_to(size // 100, blocksize)))

                print(f'Reading {size} bytes from @{addr:06X} into "{path}"...')

                tq = tqdm(desc='Reading', total=size, unit='B', unit_divisor=1024, unit_scale=True)

                try:
                    with open(path, 'wb') as f:
                        done = 0
                        while done < size:
                            n = min(io_size, size-done)

                            f.write(execcmd(make_cb(NitDlCmd.DEV_READ, arg1=addr+done, arg3=n), recv=n))

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

                                execcmd(make_cb(NitDlCmd.DEV_WRITE, arg1=addr+done, arg3=len(block)), send=block)

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
        execcmd(make_cb(BlCmd.REBOOT))

###############################################################################

if have_uart and args.port is not None:
    with Serial(args.port) as port:
        udl = UARTDownload(port)

        print('Trying to synchronize.', end='')

        port.timeout = .01

        try:
            done = False

            num = 0
            turn = 0

            while not done:
                if num < 10:
                    # send a sync pattern
                    udl.port.reset_input_buffer()
                    udl.port.write(UARTDownload.SYNC_TOKEN)
                    while not done:
                        recv = udl.port.read(4)
                        if recv == b'': break
                        if recv == UARTDownload.SYNC_RESP:
                            done = True

                    num += 1

                else:
                    print('.', end='', flush=True)

                    if turn == 0:
                        # send reset packet in initial baud rate
                        udl.port.baudrate = args.init_baud
                        udl.send_reset(True)
                        turn = 1

                    elif turn == 1:
                        # send reset packet in target baud rate
                        udl.port.baudrate = args.baud
                        udl.send_reset(True)
                        udl.port.baudrate = args.init_baud
                        turn = 0

                    num = 0

        except Exception as e:
            print(' failed:')
            raise e

        else:
            print(' done.')

        port.timeout = .1

        def execcmd(cb, send=None, recv=None, max_io=512, switch_baud=None):
            # first goes the command block
            udl.send_packet(cb)

            # switch baudrate at that point
            if switch_baud is not None:
                port.baudrate = switch_baud

            # transfer data
            if send is not None:
                # send data blocks
                sent = 0
                while sent < len(send):
                    num = min(len(send) - sent, max_io)

                    udl.send_packet(send[sent : sent+num])
                    sent += num

            elif recv is not None:
                # receive data blocks
                data = b''
                while len(data) < recv:
                    num = min(recv - len(data), max_io)

                    block = udl.recv_packet()
                    data += block

                    if len(block) != num:
                        break

                return data

        do_the_stuff(execcmd, 512, 'uart')

elif have_scsi and args.mscdev is not None:
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
