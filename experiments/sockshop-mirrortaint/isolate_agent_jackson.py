"""Relocate the private JSON implementation, preserving class-file CP indices.

Only Jackson dependencies and explicitly internal JSON users are rewritten.
Business inspector literal class names and instrumentation descriptors stay native.
ASCII package prefixes in modified UTF8 entries can be replaced as bytes, without
decoding/re-encoding unrelated modified UTF8 (including supplementary characters).
"""
import struct

OLD = b'com/fasterxml/jackson/'
NEW = b'tracefusion/internal/jackson/'
INTERNAL_USERS = ('PlannedServiceAgent', 'SourceEvidenceHooks', 'ExecutionKernelHooks')


def relocate(data):
    assert data[:4] == b'\xca\xfe\xba\xbe'
    count = struct.unpack_from('>H', data, 8)[0]
    result = bytearray(data[:10]); pos = 10; index = 1
    sizes = {3: 4, 4: 4, 5: 8, 6: 8, 7: 2, 8: 2, 9: 4, 10: 4,
             11: 4, 12: 4, 15: 3, 16: 2, 17: 4, 18: 4, 19: 2, 20: 2}
    while index < count:
        tag = data[pos]; pos += 1; result.append(tag)
        if tag == 1:
            length = struct.unpack_from('>H', data, pos)[0]; pos += 2
            value = data[pos:pos + length]; pos += length
            value = value.replace(OLD, NEW).replace(OLD.replace(b'/', b'.'), NEW.replace(b'/', b'.'))
            assert len(value) <= 65535
            result.extend(struct.pack('>H', len(value))); result.extend(value)
        else:
            size = sizes[tag]; result.extend(data[pos:pos + size]); pos += size
            if tag in (5, 6): index += 1
        index += 1
    result.extend(data[pos:]); return bytes(result)


def agent_class(name, data):
    if name.startswith(OLD.decode()):
        return name.replace(OLD.decode(), NEW.decode(), 1), relocate(data)
    if name.split('$', 1)[0].removesuffix('.class') in INTERNAL_USERS:
        return name, relocate(data)
    return name, data


def symbolic_types(data):
    """Type-bearing CP entries and declared descriptors, excluding String literals."""
    count = struct.unpack_from('>H', data, 8)[0]; pos = 10; index = 1
    utf = {}; references = []
    sizes = {3:4,4:4,5:8,6:8,7:2,8:2,9:4,10:4,11:4,12:4,15:3,16:2,17:4,18:4,19:2,20:2}
    while index < count:
        tag = data[pos]; pos += 1
        if tag == 1:
            size = struct.unpack_from('>H',data,pos)[0]; pos += 2
            utf[index] = data[pos:pos+size]; pos += size
        else:
            if tag in (7,16): references.append(struct.unpack_from('>H',data,pos)[0])
            if tag == 12: references.append(struct.unpack_from('>H',data,pos+2)[0])
            pos += sizes[tag]
            if tag in (5,6): index += 1
        index += 1
    pos += 6
    interfaces = struct.unpack_from('>H',data,pos)[0]; pos += 2+2*interfaces
    for _ in range(2):
        members = struct.unpack_from('>H',data,pos)[0]; pos += 2
        for _ in range(members):
            references.append(struct.unpack_from('>H',data,pos+4)[0])
            attrs = struct.unpack_from('>H',data,pos+6)[0]; pos += 8
            for _ in range(attrs):
                length = struct.unpack_from('>I',data,pos+2)[0]; pos += 6+length
    return [utf[i] for i in references]
