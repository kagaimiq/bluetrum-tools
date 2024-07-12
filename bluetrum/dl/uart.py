from bluetrum.crc import ab_crc16
import time

class UARTDownload:
    SYNC_TOKEN  = b'\xA5\x96\x87\x5A'   # Sync token
    SYNC_RESP   = b'\x5A\x69\x78\xA5'   # Sync response
    RESET_TOKEN = b'\xF5\xA0'           # Communication Reset token (sending sync token next to it resets the chip instead)

    ACK_RESP     = 0x1E   # Acknowledge
    NACK_RESP    = 0x2D   # Negative acknowledge
    OKAY_RESP    = 0x3C   # this is used to indicate the chip didn't yet processed the last sent packet
    DATA_TOKEN   = 0x4B   # Data token
    DATA_REQUEST = 0xB4   # Request for data
    WHAT_TOKEN   = 0xC3   # ???

    #------------------------------------------

    def __init__(self, port):
        self.port = port
        self.comms_reset()

    def port_read(self, size):
        data = self.port.read(size)
        if len(data) < size:
            raise TimeoutError(f'Not enough data has been received from the port (had only {len(data)} bytes)')
        return data

    def port_write(self, data):
        self.port.write(data)
        # consume the echo back
        echo = self.port.read(len(data))
        if len(echo) < len(data):
            raise TimeoutError('Did not receive the echo back')
        #if echo != data:
        #    raise ValueError('The echo has been corrupted')

    def comms_reset(self):
        self.counter = 0

    def send_reset(self, hard=False):
        if not hard:
            # communication soft-reset
            self.port_write(UARTDownload.RESET_TOKEN)
        else:
            # chip hard-reset
            self.port_write(UARTDownload.RESET_TOKEN + UARTDownload.SYNC_TOKEN)

        # this makes sense
        self.comms_reset()

    def send_packet(self, data):
        # construct the data packet
        self.counter = (self.counter + 1) & 0xFF
        packet = bytes([UARTDownload.DATA_TOKEN, self.counter])
        packet += len(data).to_bytes(2, 'little') + data + ab_crc16(data).to_bytes(2, 'little')

        # try to send it   (TODO better approach)
        llcnt = tries = 0
        while tries < 100:
            self.port_write(packet)

            # response
            try:
                resp = self.port_read(2)
            except TimeoutError:
                # maybe a CRC error or reception failure
                if llcnt > 10:
                    raise TimeoutError('Link lost')
                llcnt += 1
                continue

            llcnt = 0

            if resp[1] != self.counter:
                raise RuntimeError(f'Invalid counter value in response ({resp[1]}) vs. the packet ({packet[1]})')

            if resp[0] == UARTDownload.ACK_RESP:
                # All fine
                return
            elif resp[0] == UARTDownload.OKAY_RESP:
                # Received fine, but the previous data block hasn't been processed yet.
                return
            elif resp[0] == UARTDownload.NACK_RESP:
                # Failed, perhaps the chip is busy.
                time.sleep(.2)
            else:
                raise RuntimeError(f'Unexpected response token {resp[0]:02X}')

            tries += 1

        raise TimeoutError('The chip could not accept the data block')

    def recv_packet(self):
        # construct the data request
        self.counter = (self.counter + 1) & 0xFF
        request = bytes([UARTDownload.DATA_REQUEST, self.counter])

        # try to get the data   (TODO better approach)
        llcnt = tries = 0
        while tries < 100:
            self.port_write(request)

            # response
            try:
                resp = self.port_read(2)
            except TimeoutError:
                # maybe chip didn't receive the request
                if llcnt > 10:
                    raise TimeoutError('Link lost')
                llcnt += 1
                continue

            llcnt = 0

            if resp[1] != self.counter:
                raise RuntimeError(f'Invalid counter value in response ({resp[1]}) vs. the packet ({request[1]})')

            if resp[0] == UARTDownload.DATA_TOKEN:
                # Here's the data
                size = int.from_bytes(self.port_read(2), 'little')
                data = self.port_read(size)
                crc = int.from_bytes(self.port_read(2), 'little')
                if ab_crc16(data) != crc:
                    # You can't redo it because the chip thinks it did send the data back successfully
                    raise ValueError('Received data block CRC mismatch')
                return data
            elif resp[0] == UARTDownload.NACK_RESP:
                # Failed, chip does not have any data block yet.
                time.sleep(.05)
            else:
                raise RuntimeError(f'Unexpected response token {resp[0]:02X}')

            tries += 1

        raise TimeoutError('The chip did not any data packet to respond with')
