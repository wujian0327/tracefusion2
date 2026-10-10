"""Small independent class-file reader for the collector's bounded JVM subset.

No ASM, javap, collector plan, fixture names, or expected answers are used to decode.
Unrecognized executable opcodes fail closed. This is not a general class verifier.
"""
class Reader:
    def __init__(self, data): self.data, self.pos = data, 0
    def take(self, n):
        if n < 0 or self.pos + n > len(self.data): raise ValueError("truncated class file")
        b = self.data[self.pos:self.pos+n]; self.pos += n
        return b
    def u1(self): return self.take(1)[0]
    def u2(self): return int.from_bytes(self.take(2), "big")
    def u4(self): return int.from_bytes(self.take(4), "big")
    def signed(self, n): return int.from_bytes(self.take(n), "big", signed=True)


def descriptor(desc):
    def one(i):
        if i >= len(desc): raise ValueError("truncated descriptor")
        if desc[i] in "IZBCS": return "int", i + 1
        if desc[i] == "L":
            end = desc.find(";", i)
            if end <= i + 1: raise ValueError("invalid reference descriptor")
            return "ref", end + 1
        raise ValueError("unsupported descriptor " + desc)
    if not desc.startswith("("): raise ValueError("method descriptor required")
    args, i = [], 1
    while i < len(desc) and desc[i] != ")":
        t, i = one(i); args.append(t)
    if i >= len(desc): raise ValueError("missing descriptor return")
    i += 1
    if desc[i:] == "V": ret, i = "void", i + 1
    else: ret, i = one(i)
    if i != len(desc): raise ValueError("descriptor trailing bytes")
    return args, ret


def read_class(data, fields_only=False):
    r = Reader(data)
    if r.u4() != 0xcafebabe: raise ValueError("class magic")
    minor, major = r.u2(), r.u2()
    if not 45 <= major <= 61 or minor == 65535: raise ValueError("class version outside Java 17 contract")
    cp = [None] * r.u2()
    i = 1
    while i < len(cp):
        tag = r.u1()
        if tag == 1: value = r.take(r.u2()).decode("utf-8")  # reject unsupported modified UTF-8 forms
        elif tag == 3: value = r.signed(4)
        elif tag == 4: value = r.take(4)
        elif tag in (5, 6): value = r.take(8)
        elif tag in (7, 8, 16, 19, 20): value = r.u2()
        elif tag in (9, 10, 11, 12, 17, 18): value = (r.u2(), r.u2())
        elif tag == 15: value = (r.u1(), r.u2())
        else: raise ValueError("unknown constant-pool tag")
        cp[i] = (tag, value)
        i += 2 if tag in (5, 6) else 1

    def get(index, tags):
        if index <= 0 or index >= len(cp) or cp[index] is None or cp[index][0] not in tags:
            raise ValueError("constant-pool type/index")
        return cp[index][1]
    def utf(index): return get(index, (1,))
    def cls(index): return utf(get(index, (7,)))
    def member(index, field):
        owner, nt = get(index, (9,) if field else (10, 11))
        name, desc = get(nt, (12,))
        return cls(owner) + "." + utf(name) + (":" if field else "") + utf(desc)
    def attributes(reader):
        result = {}
        for _ in range(reader.u2()):
            name = utf(reader.u2())
            if name in result: raise ValueError("duplicate attribute")
            result[name] = reader.take(reader.u4())
        return result

    access, name, superclass = r.u2(), cls(r.u2()), r.u2()
    for _ in range(r.u2()): r.u2()
    fields = {}
    for _ in range(r.u2()):
        flags, field, desc = r.u2(), utf(r.u2()), utf(r.u2())
        fields[name + "." + field + ":" + desc] = flags
        attributes(r)
    methods = {}
    for _ in range(r.u2()):
        flags, method, desc = r.u2(), utf(r.u2()), utf(r.u2())
        attrs = attributes(r)
        if fields_only or method == "<init>": continue
        if flags & (0x8 | 0x100 | 0x400 | 0x20) != 0x8: raise ValueError("method access contract")
        descriptor(desc)
        if "Code" not in attrs: raise ValueError("method has no code")
        code = Reader(attrs["Code"])
        max_stack, max_locals = code.u2(), code.u2()
        raw = code.take(code.u4())
        if code.u2(): raise ValueError("exception table outside contract")
        attributes(code)
        if code.pos != len(code.data): raise ValueError("trailing code data")
        b, instructions = Reader(raw), []
        while b.pos < len(raw):
            offset, op, operands = b.pos, b.u1(), []
            if op in (16, 17): operands = [b.signed(1 if op == 16 else 2)]
            elif op in (18, 19):
                operands = [get(b.u1() if op == 18 else b.u2(), (3,))]; op = 18
            elif op in (21, 25, 54, 58): operands = [b.u1()]
            elif 26 <= op <= 29: operands, op = [op - 26], 21
            elif 42 <= op <= 45: operands, op = [op - 42], 25
            elif 59 <= op <= 62: operands, op = [op - 59], 54
            elif 75 <= op <= 78: operands, op = [op - 75], 58
            elif op == 132: operands = [b.u1(), b.signed(1)]
            elif 153 <= op <= 167 or op in (198, 199): operands = [offset + b.signed(2)]
            elif op == 200: operands, op = [offset + b.signed(4)], 167
            elif op in (180, 181, 184): operands = [member(b.u2(), op != 184)]
            elif op == 196:
                op = b.u1()
                if op not in (21, 25, 54, 58, 132): raise ValueError("unsupported wide opcode")
                operands = [b.u2()]
                if op == 132: operands.append(b.signed(2))
            elif op not in {0, 1, 2, 3, 4, 5, 6, 7, 8, 87, 89, 95, 96, 100, 104, 108,
                            112, 116, 120, 122, 124, 126, 128, 130, 145, 146, 147, 172, 176, 177}:
                raise ValueError("unsupported raw opcode " + str(op))
            instructions.append(dict(offset=offset, opcode=op, operands=operands))
        offsets = {p["offset"]: i for i, p in enumerate(instructions)}
        full = name + "." + method + desc
        plans = []
        for index, p in enumerate(instructions):
            op, operands = p["opcode"], p["operands"]
            if 153 <= op <= 167 or op in (198, 199):
                if operands[0] not in offsets: raise ValueError("branch into non-instruction")
                operands = [offsets[operands[0]]]
            plans.append(dict(site=full + "@" + str(index), method=full, pc=index, opcode=op, operands=operands))
        methods[full] = dict(plans=plans, max_stack=max_stack, max_locals=max_locals, descriptor=desc)
    attributes(r)
    if r.pos != len(data): raise ValueError("trailing class data")
    return dict(name=name, fields=fields, methods=methods)
