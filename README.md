# Bluetrum Tools

Some tools for some obscure RISC-V bluetooth audio chips made by Bluetrum (the "AB"/"A3" branded chips).
These ones seem to begin dominating the low-end previously held with chips made by companies such as JieLi or Buildwin.

## What's up

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
       '--- **anything else**    <== resource files

```

If you have a flash dump, most likely than not you need to obtain the "userkey" (maybe I'll use a different term afterwards)
that is used for the scrambling of the code area (like the "chipkey" in JieLi chips).
information on obtaining the "userkey" as well as how to dump the firmware out of the chip is coming soon...

### fwmake1.py

A firmware maker. Makes a firmware that is almost byte-exact to the vendor's firmwares.
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
