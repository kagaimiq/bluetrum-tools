# Bluetrum Tools

Some tools for some obscure RISC-V bluetooth audio chips made by Bluetrum (the "AB"/"A3" branded chips).
These ones seem to begin dominating the low-end previously held with chips made by companies such as JieLi or Buildwin.

## What's up

### download.py

A simple tool that allows to read and write flash of an bluetrum chip.

It supports both the USB and UART interfaces.

For the USB interface it depends on the `scsiio` library which I have made myself and I haven't bothered making it a proper package so if you want you can rip it off [jl-uboot-tool](https://github.com/kagaimiq/jl-uboot-tool), however getting into the USB bootloader is a much more involved task than getting into the UART bootloader so you probably won't care about that one anyway.

For UART interface you just need an UART brigde and a way to mix the TX and RX signals together (this tool assumes any data sent over TX is also echoed back into RX), and possibly a way to shift the levels to 3.3v if it isn't by now.

Then you just need to find an UART download pin (which is usually the PB3 GPIO; if your device has an USB port that is wired to the chip, it would be on the D+ pin), run the tool with an appropriate port specified, connect the UART to the chip, and then apply power to the chip.

The tool then should successfully sync with the chip and be able to talk with it:

```
$ python3 download.py --port /dev/ttyUSB0
Trying to synchronize..
Got it!
 Chip ID:       b'BLUEPRAO\x01\x00\x00\x00'
 Load address:  $00012000
 Init. commkey: $54E0CD2F
 New commkey:   $B80D21C2
Changing baudrate to 921600 baud...
- Title: b'dlblob ver 0.01\x00'
- Code key: >>>>5C3CEDB4<<<<
- Flash ID: 85 60 13 85 60 13 85 60 13 85 60 13 ...
  - Flash size: 524288 bytes
```

If no action was specified, it will just print out some basic info like the chip ID and, if the code blob has successfully ran without any issues, the "code key" and the flash ID (with its size calculated in a naive way) would be also displayed.

The `-r`/`--reboot` option can be used to reboot the chip after the tool has done doing its thing.

As for the actual operation, the type of the operation is specified as `read`, `write` or `erase` (at present it can do only a single type of operation at a time), and the parameters (address, size and path) follow.

The `read` operaton takes one or more pairs of `<address> <size> <file>`, that will dump an area of `<size>` bytes (zero means 'whole flash') starting at `<address>` into file `<file>`.

The `write` operation takes one or more pairs of `<address> <file>`, that will write the `<file>` into the flash starting at `<address>`.
The erase of the section is performed automatically, so you don't have to do it manually, and the address/size alignment situation needs to be considered.

The `erase` operation takes one or more pairs of `<address> <size>` and erases an area of `<size>` bytes (again, zero means 'whole flash') starting at `<address>`. Note that the address and size will be adjusted to the size of an small eraseblock (4096 bytes).

----

This tool has been tested only with the "PRAO" chips, so it's not guaranteed to work on other chips (with the code blob being a biggest concern).
Also it assumes the chip has an SPI NOR flash chip attached internally to GPIOG, so no OTP chips, or an SPI NAND, I²C EEPROM or whatever might be on/with your chip.

### fwunpack.py

A firmware image unpacker.

Each supplied image is unpacked to a respective `<image filename>_unpack` directory, that has a following structure:
```
 <image>_unpack
  |--- decrypted.bin     <== the image after all of the decryption processes were performed with it
  |--- header.bin        <== the image's boot header and boot code (in a format used by the xmaker, etc)
  |--- boot-code.bin     <== the boot code itself (without any metadata such as the load address, etc.)
  |--- app.bin           <== main application code blob
  |--- res.bin           <== resources blob
  '--- res               <== unpacked resources
       |--- 00__order__00.txt    <== file that has the original order of the resources
       '--- **everything else**  <== resource files

```

If you have a flash dump, most likely than not you need to obtain the key that is used for the scrambling of the code area.

### fwmake1.py

A firmware image maker.

The result is byte-exact to the ones found to be made with the vendor's tools (xmaker);
One difference right now is that additional stuff residing in the header area (i.e. everything except the boot header, boot code and the region table with its CRC)
is not being generated, since I haven't figured out them well enough,
meaning that it's not yet suitable to be used to modify the firmware (previously decomposed with the `fwunpack.py` script above, for example).

The `--no-res-scramble` option disables the scrambling of the resource blob area, if you so desire.
Note that a proper resource blob is not automatically generated if you e.g. specify a directory instead of a file, instead it should be generated separately somehow.

### mkheader.py

Makes the `header.bin` file (or a minimal bootable image, if such option has been provided with a `-b`/`--bootagle` flag).

## Resources

- Bluetrum seemingly-official [GitHub](https://github.com/BLUETRUM) and [Gitee](https://gitee.com/Bluetrum) organizations
  * Here you can find some resources for the "AB32VG1" chip (the CRWN/Crown chip), but really nothing else. (still better than nothing at all!)
- [Their website](https://www.bluetrum.com/)
- [Random SDK dump repo](https://github.com/ZhiqingLi/Sdk_Refresh) containing among other things, SDKs for the Bluetrum Crown (AB530x) and Epic (AB532x) chips.
