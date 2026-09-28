#!/usr/bin/env python3
"""Write tests/differential_tests.nv from Python's bencode.py.

`bencode.py`, version 4.1.0, is an independent bencode implementation
whose encoder sorts dictionary keys as BEP 3 requires.  It is not in the
standard library; install
it into a virtual environment and run the script with that interpreter:

    python3 -m venv /tmp/benc-venv
    /tmp/benc-venv/bin/pip install bencode.py==4.1.0
    /tmp/benc-venv/bin/python tools/differential.py

Run from the package root.  The output is passed through `novo fmt`.

Three tables are written, each from a fixed seed:

1. canonical: a value bencode.py encoded, in hexadecimal.  Reading it
   and writing it back must give the same bytes.
2. unsorted: a value written with its dictionaries in the order they
   were built, in hexadecimal, bencode.py's sorted encoding of the same
   value, and the offset of the first byte where the two differ.
3. torrents: a `.torrent` file, some with an `info` dictionary whose
   keys are out of order, the bytes its `info` dictionary occupies,
   which are what the info-hash is taken over, its name, its total
   length, its piece count and its number of files.
"""
import os
import random
import subprocess

import bencodepy

SEED = 20260928


def gen(rng, depth):
    """A random value: ints, byte strings, lists and dictionaries."""
    kind = rng.choice(['int', 'bytes', 'list', 'dict'] if depth < 3 else ['int', 'bytes'])
    if kind == 'int':
        return rng.choice([0, -1, 7, 2 ** 63 - 1, -2 ** 63, rng.randint(-10 ** 12, 10 ** 12)])
    if kind == 'bytes':
        return bytes(rng.randrange(256) for _ in range(rng.randint(0, 8)))
    if kind == 'list':
        return [gen(rng, depth + 1) for _ in range(rng.randint(0, 4))]
    keys = set()
    out = {}
    for _ in range(rng.randint(0, 5)):
        k = bytes(rng.choice(b'aZb_0 ') for _ in range(rng.randint(0, 3)))
        if k not in keys:
            keys.add(k)
            out[k] = gen(rng, depth + 1)
    return out


def as_is(v):
    """The encoding with every dictionary in the order it was built."""
    if isinstance(v, int):
        return b'i%de' % v
    if isinstance(v, bytes):
        return b'%d:' % len(v) + v
    if isinstance(v, list):
        return b'l' + b''.join(as_is(x) for x in v) + b'e'
    return b'd' + b''.join(as_is(k) + as_is(x) for k, x in v.items()) + b'e'


def shuffled(v, rng):
    """The same value with every dictionary's order shuffled."""
    if isinstance(v, list):
        return [shuffled(x, rng) for x in v]
    if isinstance(v, dict):
        items = list(v.items())
        rng.shuffle(items)
        return {k: shuffled(x, rng) for k, x in items}
    return v


def first_difference(a, b):
    for i in range(min(len(a), len(b))):
        if a[i] != b[i]:
            return i
    return -1


def nv(text):
    return '"' + text.replace('\\', '\\\\').replace('"', '\\"').replace('$', '\\$') + '"'


def torrent(rng, multi):
    pieces = bytes(rng.randrange(256) for _ in range(20 * rng.randint(1, 4)))
    info = {b'name': b'data-%d' % rng.randint(0, 99), b'piece length': 16384, b'pieces': pieces}
    if multi:
        files = [{b'length': rng.randint(0, 50000), b'path': [b'dir', b'f%d.bin' % i]}
                 for i in range(rng.randint(1, 3))]
        info[b'files'] = files
        total = sum(f[b'length'] for f in files)
        count = len(files)
    else:
        total = rng.randint(1, 60000)
        info[b'length'] = total
        count = 1
    if rng.random() < 0.5:
        info[b'private'] = 1
    top = {b'announce': b'http://tracker.example/announce', b'info': info,
           b'creation date': 1700000000, b'comment': b'a test'}
    return top, total, count


def main():
    rng = random.Random(SEED)
    canonical = []
    for _ in range(40):
        v = gen(rng, 0)
        canonical.append('    %s' % nv(bencodepy.encode(v).hex()))
    unsorted = []
    while len(unsorted) < 20:
        v = shuffled(gen(rng, 0), rng)
        raw = as_is(v)
        sorted_ = bencodepy.encode(v)
        at = first_difference(raw, sorted_)
        if at < 0:
            continue
        unsorted.append('    (%s, %s, %d)' % (nv(raw.hex()), nv(sorted_.hex()), at))
    torrents = []
    for i in range(12):
        top, total, count = torrent(rng, i % 2 == 1)
        if i % 3 == 0:
            info = shuffled(top[b'info'], rng)
            body = as_is(info)
            raw = (b'd8:announce' + as_is(top[b'announce']) + b'7:comment' + as_is(top[b'comment'])
                   + b'13:creation date' + as_is(top[b'creation date']) + b'4:info' + body + b'e')
        else:
            body = bencodepy.encode(top[b'info'])
            raw = bencodepy.encode(top)
        start = raw.index(b'4:info') + 6
        span = raw[start:start + len(body)]
        assert span == body
        pieces = len(top[b'info'][b'pieces']) // 20
        torrents.append('    (%s, %s, %s, %d, %d, %d)' % (
            nv(raw.hex()), nv(span.hex()), nv(top[b'info'][b'name'].decode()), total, pieces, count))
    text = HEADER
    text += '\n// Canonical encodings, in hexadecimal.\nfn canonical_rows() -> [Str]\n    [' + ',\n'.join(canonical).lstrip() + ']\n'
    text += ('\n// Unsorted encodings, the sorted encoding of the same value, and the\n'
             '// first offset where they differ.\n')
    text += 'fn unsorted_rows() -> [(Str, Str, Int)]\n    [' + ',\n'.join(unsorted).lstrip() + ']\n'
    text += ('\n// Torrent files: the file, the bytes of its `info`, its name,\n'
             '// total length, piece count and file count.\n')
    text += 'fn torrent_rows() -> [(Str, Str, Str, Int, Int, Int)]\n    [' + ',\n'.join(torrents).lstrip() + ']\n'
    text += FOOTER
    path = os.path.join('tests', 'differential_tests.nv')
    open(path, 'w').write(text)
    subprocess.run(['novo', 'fmt', path], check=True)


HEADER = '''// differential_tests.nv — this package against Python's bencode.py
// 4.1.0.
//
// Written by tools/differential.py; do not edit by hand.

use std.test
use std.bytes
use bencread
use bencwrite
use benctorrent
'''

FOOTER = '''
// A buffer from hexadecimal.
fn unhex(text: Str) -> Bytes
    bytes.from_hex(text) ?? bytes.zeros(0)

@test
fn test_a_canonical_encoding_reads_and_writes_back_unchanged() [io]
    for hex in canonical_rows()
        test.case(hex)
        let src = unhex(hex)
        test.assert(bencwrite.is_canonical(src))
        test.assert_none(bencwrite.first_difference(src))
        match bencread.read(src)
            Err(e) => test.fail(e.message())
            Ok(v)  =>
                test.assert_eq_str(bytes.to_hex(bencwrite.write(v)), hex)
                test.assert_eq(bencwrite.encoded_len(v), bytes.len(src))
        match bencread.validate(src)
            Err(e) => test.fail(e.message())
            Ok(ok) => test.assert(ok)

@test
fn test_an_unsorted_encoding_is_kept_as_is_and_sorted_on_request() [io]
    for (raw, sorted, at) in unsorted_rows()
        test.case(raw)
        let src = unhex(raw)
        test.assert(not bencwrite.is_canonical(src))
        test.assert_eq(bencwrite.first_difference(src) ?? -1, at)
        match bencread.read(src)
            Err(e) => test.fail(e.message())
            Ok(v)  =>
                test.assert_eq_str(bytes.to_hex(bencwrite.write_as_is(v)), raw)
                test.assert_eq_str(bytes.to_hex(bencwrite.write(v)), sorted)

@test
fn test_the_info_hash_is_taken_over_the_bytes_the_file_has() [io]
    for (hex, span, name, total, pieces, files) in torrent_rows()
        test.case(name)
        let src = unhex(hex)
        match benctorrent.info_hash_input(src)
            Err(e) => test.fail(e.message())
            Ok(b)  => test.assert_eq_str(bytes.to_hex(b), span)
        match benctorrent.read(src)
            Err(e) => test.fail(e.message())
            Ok(t)  =>
                test.assert_eq_str(t.info.name, name)
                test.assert_eq(benctorrent.total_length(t.info), total)
                match benctorrent.piece_count(t.info)
                    Ok(n)  => test.assert_eq(n, pieces)
                    Err(e) => test.fail(e.message())
                test.assert_eq(list.len(t.info.files), files)
'''

if __name__ == '__main__':
    main()
