"""Independent GIF89a bit-stream/LZW reference, not an instruction interpreter.

Only ordinary, single-image, non-interlaced, global-palette GIFs are accepted.
The inference module must never import this module or consume its code rows.
Specification: https://giflib.sourceforge.net/gifstandard/GIF89a.html (Appendix F).
"""
from dataclasses import dataclass


def require(ok, message):
    if not ok:
        raise ValueError(message)


@dataclass
class ImageData:
    width: int
    height: int
    palette: bytes
    descriptor: int
    minimum: int
    payload: bytes
    offsets: list
    blocks: list


def parse(data):
    require(len(data) >= 14 and data[:6] in (b'GIF87a', b'GIF89a'), 'Not a GIF')
    width = int.from_bytes(data[6:8], 'little')
    height = int.from_bytes(data[8:10], 'little')
    require(0 < width * height <= 65536 and data[10] & 128, 'Unsupported canvas/palette')
    palette_end = 13 + 3 * (2 << (data[10] & 7))
    require(palette_end < len(data), 'Truncated global palette')
    palette = data[13:palette_end]
    p = palette_end
    # Normal generated fixtures have no extensions. Reject instead of silently
    # deriving different image/control semantics from unmodeled extension data.
    require(data[p] == 0x2c and p + 11 < len(data), 'Requires one image without extensions')
    descriptor = p
    require(data[p+1:p+5] == bytes(4), 'Requires zero image origin')
    require(int.from_bytes(data[p+5:p+7], 'little') == width and
            int.from_bytes(data[p+7:p+9], 'little') == height, 'Canvas/image mismatch')
    require(data[p+9] == 0, 'Local palette/interlace unsupported')
    minimum = data[p+10]
    require(2 <= minimum <= 8, 'Unsupported LZW minimum size')
    p += 11
    payload, offsets, blocks = bytearray(), [], []
    while True:
        require(p < len(data), 'Missing sub-block terminator')
        n = data[p]
        p += 1
        if not n:
            break
        require(p+n <= len(data), 'Truncated data block')
        blocks.append(dict(length_offset=p-1, data_offset=p, length=n))
        payload.extend(data[p:p+n])
        offsets.extend(range(p, p+n))
        p += n
    require(data[p:] == b';', 'Requires exactly one image and trailer')
    return ImageData(width, height, palette, descriptor, minimum, bytes(payload), offsets, blocks)


def decode(image):
    """Decode independently, retaining the source bit window of each code.

    Code width comes from this reference's own dictionary, never from captured
    target context, selector, returned code values, or inferred source labels.
    """
    clear = 1 << image.minimum
    eoi = clear + 1
    table = {}
    width = image.minimum + 1
    next_code = clear + 2
    previous = None
    bit = 0
    pixels = bytearray()
    codes = []
    while len(codes) < 131072:
        require(bit+width <= len(image.payload)*8, 'Incomplete code')
        value = sum(((image.payload[(bit+k)//8] >> ((bit+k)%8)) & 1) << k for k in range(width))
        labels = sorted({image.offsets[(bit+k)//8] for k in range(width)})
        codes.append(dict(sequence=len(codes)+1, value=value, width=width,
                          payload_bit_start=bit, source_file_offsets=labels,
                          source_bits=[[image.offsets[(bit+k)//8], (bit+k)%8] for k in range(width)]))
        bit += width
        if value == clear:
            table = {i: bytes([i]) for i in range(clear)}
            next_code, width, previous = clear+2, image.minimum+1, None
            continue
        if value == eoi:
            require(len(pixels) == image.width * image.height, 'Decoded pixel count mismatch')
            return codes, bytes(pixels)
        require(table, 'Missing initial clear')
        if value in table:
            entry = table[value]
        elif value == next_code and previous is not None:
            entry = previous + previous[:1]
        else:
            raise ValueError('Invalid dictionary code')
        pixels.extend(entry)
        require(len(pixels) <= image.width*image.height, 'Too many decoded pixels')
        if previous is not None and next_code < 4096:
            table[next_code] = previous + entry[:1]
            next_code += 1
            if next_code == 1 << width and width < 12:
                width += 1
        previous = entry
    raise ValueError('Reference code budget exceeded')
