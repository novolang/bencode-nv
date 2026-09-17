# bencode-nv

Bencode is the encoding BitTorrent is written in. It is specified in
[BEP 3](https://www.bittorrent.org/beps/bep_0003.html), the BitTorrent
protocol specification, and it is what a `.torrent` file and the peer
protocol's extension messages are made of. This package reads and writes
it in novo-lang, and reads a `.torrent` file into typed values on top of
it.

**Status: NOT IMPLEMENTED — interface only.** Every function is declared
with its full signature, but every body is a `todo()` that panics when
called. The package is published so its design can be reviewed and
depended on before it is implemented. Version 0.1.0 will be the first
working release.

## What bencode is

Four types, and nothing else.

| Type | Written | Example |
| --- | --- | --- |
| Integer | `i`, the digits, `e` | `i3e`, `i-3e` |
| Byte string | the length, `:`, the bytes | `4:spam` |
| List | `l`, the values, `e` | `l4:spam4:eggse` |
| Dictionary | `d`, key and value pairs, `e` | `d3:cow3:moo4:spam4:eggse` |

There is no boolean, no null, no floating-point number and no
whitespace. A torrent's `private` flag is the integer 1, and its
creation date is a number of seconds since the Unix epoch.

A dictionary's keys are byte strings. BEP 3 requires a writer to sort
them **as raw byte strings**, which is not the same as sorting as text:
`"Z"` sorts before `"a"`, because `0x5A` is below `0x61`.

Everything the format could have left open, BEP 3 closed. An integer
has no leading zeros and there is no `i-0e`. A byte string's length has
no leading zeros. So a value written twice is the same bytes twice, and
a dictionary's key order is the only thing two correct writers can
disagree about.

## What a torrent file is

A bencoded dictionary. Its `announce` member is a tracker's URL. Its
`info` member is a dictionary describing the data: a `name`, a
`piece length`, and a `pieces` member that is every piece's SHA-1
digest concatenated, twenty bytes each.

`info` then describes the data in one of two ways and never both: a
`length`, for a single file, or a `files` list of dictionaries each with
its own `length` and a `path` given as a list of components.

A torrent's identity — its **info-hash** — is the SHA-1 of the `info`
dictionary's **encoded bytes**. Not of the values in it: of the bytes.

## Why that matters, and what this package does about it

Re-encoding the values of `info` and hashing the result gives the right
answer only when the file was written canonically. Files in the wild are
not always: a dictionary whose keys are out of order, a member a client
appended after sorting, a spelling nobody else uses. Any of those
produces a different hash, and a different hash is a different torrent.
The client joins a swarm nobody is in, and reports nothing wrong.

So this package has two readers.

**`bencread.read`** answers the values. It is what a caller that wants
the contents of a file uses.

**`bencread.read_tree`** answers the same values in an arena of numbered
nodes, each carrying the half-open byte range it occupied in the buffer.
`bencread.slice` hands back those exact bytes.

`benctorrent.info_span` is the one call the arrangement exists for: it
answers the byte range of the `info` dictionary in one scan, with no
tree built and no allocation for the values, and the caller hashes that
range.

**The hash itself is not computed here.** The caller hands the bytes to
[crypto-nv](https://novo-lang.org/packages/crypto-nv), whose `sha1` is
the one function needed. So this package links no hash function, and a
BEP 52 version 2 torrent — whose info-hash is SHA-256 over the same
span — needs a different call at the caller's end and no change here.

## Install

```
novo pkg add bencode-nv
```

## Example

```novo
use std.bytes
use bencread
use bencvalue
use benctorrent

fn main() [io]
    // The bytes of a .torrent file, which the caller read from disk.
    let raw = bytes.from_str("d8:announce3:foo4:infod3:cow3:mooee")

    match benctorrent.read(raw)
        Err(e) => println("not a torrent: ${e.message()}")
        Ok(t)  =>
            println("tracker: ${t.announce}")
            println("name: ${t.info.name}")

            // The bytes the info-hash is taken over. Hand these to
            // crypto-nv's sha1; nothing here hashes anything.
            match benctorrent.info_hash_input(raw)
                Err(e) => println(e.message())
                Ok(b)  => println("${bytes.len(b)} byte(s) to hash")

    // Reading bencode that is not a torrent.
    match bencread.read(bytes.from_str("l4:spam4:eggse"))
        Err(e) => println(e.message())
        Ok(v)  => println("${bencvalue.len(v)} element(s)")
```

Build and test with `novo pkg build` and `novo test`. Today `novo test`
fails on purpose: every test reaches a
`not implemented: bencode-nv.<module>.<fn>` panic. The tests are the
specification the implementation will have to satisfy.

## What the package contains

| Module | Contents |
| --- | --- |
| `bencerror` | Every refusal, with the byte offset it was found at. |
| `bencvalue` | The four types, the dictionary that keeps its order, and the accessors over both. |
| `bencread` | Bytes to a value, and bytes to a value that remembers where every part of it was. |
| `bencwrite` | A value back to bytes, sorted or as it stands, and the question of whether a file is already canonical. |
| `benctorrent` | The `.torrent` file, typed, and the byte range its info-hash is taken over. |

## How to choose an entry point

**`bencread.read` is for the contents of a file.** It refuses a buffer
with anything after the value, so a truncated file does not look like a
good one.

**`bencread.read_tree` is for anything that has to reproduce or hash
original bytes.** Every node carries its span, and `bencread.slice`
hands back the bytes themselves.

**`bencread.span_at` is the cheap version of that**: one scan, no tree,
for a caller that wants one range out of a large file.

**`bencwrite.write` sorts and `bencwrite.write_as_is` does not.** The
first is for producing a new torrent, which is what BEP 3 requires. The
second is for reproducing a file somebody else wrote. Choosing wrongly
changes a torrent's identity.

**`benctorrent.read` takes the whole file.** `benctorrent.from_value`
and `benctorrent.info_from_value` are for the case where the dictionary
arrived over the peer protocol's metadata extension rather than as a
file.

## The rules a user needs

1. **A byte string is bytes, not text.** BEP 3 says nothing about the
   encoding, and a torrent's `pieces` member is not text in any
   encoding. `bencvalue.as_str` is a separate accessor for the members
   that are names, and it validates nothing.
2. **A dictionary keeps the order it was read in.** Sorting on read
   would change the bytes a re-encoding produces, which changes a
   torrent's info-hash, which changes what the torrent identifies.
3. **An unsorted dictionary is read, not refused.** Files in the wild
   are not always sorted. `bencvalue.keys_sorted` is the question, and
   `bencwrite.write` is where sorting happens.
4. **A duplicate key is refused.** An unsorted dictionary still has one
   value per key; a dictionary with a key twice does not, and for a
   torrent that means two readers agree on the hash and disagree on
   what it identifies.
5. **Keys sort as raw byte strings.** `bencwrite.key_before` is that
   comparison. A sort that used a locale's collation would produce a
   different file and a different info-hash.
6. **An integer has one spelling.** `i03e` and `i-0e` are refused. An
   integer too large for sixty-four bits is refused rather than
   wrapped.
7. **A byte string's length has no leading zeros**, and a length that
   runs past the buffer is refused before anything is allocated.
8. **`bencread.read` refuses trailing bytes.** `bencread.read_prefix` is
   for a caller reading values back to back.
9. **The reader has a depth limit, and it is a value.** A list head
   costs one byte and opens a level, and a torrent file is something a
   stranger sends you.
10. **The info-hash is taken over the file's own bytes.** Use
    `benctorrent.info_span` or `benctorrent.info_hash_input`, and hash
    them with crypto-nv. Do not re-encode.
11. **A torrent is single-file or multi-file and never both.** An
    `info` with both `length` and `files`, or with neither, is
    `BencAmbiguousTorrentShape`.
12. **A single-file torrent's `files` has one entry**, whose path is
    just the name, so a caller walks one list either way.
    `info.is_single_file` is there for the caller that needs the
    distinction.
13. **An unsafe path component is refused, not cleaned.** `..`, `.`, an
    empty component and one containing a separator are all
    `BencUnsafePath`. A caller handed a cleaned path would write files
    where the torrent said, having been told nothing.
14. **`pieces` must be a whole number of twenty-byte digests.** It is
    the one corruption a torrent file can have that every other check
    passes.
15. **The last piece is shorter than the rest.**
    `benctorrent.piece_size` is the arithmetic, and it is the one every
    client gets wrong at the final piece.
16. **A piece of a multi-file torrent spans file boundaries.** The data
    is one concatenation cut into pieces afterwards, so verifying a
    piece may mean reading from several files.
    `benctorrent.files_in_piece` is that calculation.
17. **A torrent with no tracker is a torrent.** It is announced over the
    distributed hash table instead, and
    `benctorrent.is_trackerless` says so.
18. **`creation date` is the number the file holds.** This package reads
    no clock and never compares it with one.

## What is not included

- **Any hash function.** See the section above. The info-hash and a
  piece's digest are both SHA-1 the caller computes.
- **The peer wire protocol.** Handshakes, messages and choking are a
  socket and a state machine, and this package declares no effects.
- **The tracker protocol.** An announce is an HTTP request, which costs
  `[net]`.
- **The distributed hash table.** BEP 5 is a UDP protocol whose
  messages happen to be bencoded; this package reads the messages and
  is not the protocol.
- **Magnet links.** BEP 9's URI scheme carries an info-hash and no
  `info` dictionary, so parsing one is a URL parser's job and what
  comes back is not a torrent.
- **BEP 52 version 2 torrents.** Their merkle tree and their SHA-256
  info-hash are a later release. The span this package answers is the
  one they hash too.
- **Creating a torrent from files on disk.** Reading the files costs
  `[fs]`. A caller that has the pieces and their digests builds the
  dictionary with `bencvalue` and writes it with `bencwrite.write`.

## Related packages

- [crypto-nv](https://novo-lang.org/packages/crypto-nv) computes the
  SHA-1 of the span this package hands back, and of each piece.
- [cbor-nv](https://novo-lang.org/packages/cbor-nv) and
  [msgpack-nv](https://novo-lang.org/packages/msgpack-nv) are binary
  encodings with the same shape and far more types. Take one of them
  for a format that is yours to choose; take this one because
  BitTorrent chose it.
- [bson-nv](https://novo-lang.org/packages/bson-nv) is another
  length-prefixed document format, and its reader also answers a byte
  span, for the same reason.
- [url-nv](https://novo-lang.org/packages/url-nv) parses the tracker
  URLs and the magnet links this package does not.

## Test vectors

The normative source is BEP 3, which gives the grammar and the four
worked examples every implementation quotes: `i3e`, `i-3e`, `4:spam`,
`l4:spam4:eggse` and `d3:cow3:moo4:spam4:eggse`.

The oracles are the Rust crate **bendy** and the Python **bencodepy**,
each of which ships a refusal suite beside the grammar: a leading zero,
a negative zero, a length with a leading zero, a truncated string, a
non-string key, a duplicate key. The cases in this package's suite are
those.

The round-trip corpus that becomes a generated run beside them is a
directory of real `.torrent` files, where the assertion is that the
SHA-1 of `benctorrent.info_span` matches the info-hash the file is
known by — which is the only test that catches a package that
re-encodes when it should not.

```bash
novo test tests/bencode_tests.nv    # the grammar, the spans, the torrent
```

The suite asserts BEP 3's four examples, that `i03e` and `i-0e` are
refused, that a duplicate key is refused and an unsorted dictionary is
not, that the order a file had is kept, that keys sort as raw bytes so
`"Z"` precedes `"a"`, that every node remembers its span and the slice
is the original bytes, that `info_span` finds the right range, that a
`pieces` of twenty-five bytes is refused, and that a `..` path
component is refused rather than cleaned.

The tests compile today and fail at run, each on the
`not implemented: bencode-nv.<module>.<fn>` panic that is its body.
That is the expected state of an interface release. They turn green one
at a time as bodies land.

## Implementation status

| Item | Implemented |
| --- | --- |
| `bencvalue.BencValue`, `bencread.BencTree`, `benctorrent.BencTorrent` and the other types | the types are declared |
| `bencerror.offset_of`, `.code_of`, `.is_file_fault`, `BencFault.message` | no |
| `bencvalue.type_name`, `.text`, `.entry`, `.dict`, `.dict_of`, `.append`, `.len` | no |
| `bencvalue.as_int`, `.as_bytes`, `.as_str`, `.as_list`, `.as_dict`, `.key_str` | no |
| `bencvalue.get`, `.lookup`, `.has`, `.keys`, `.keys_sorted`, `.path` | no |
| `bencread.default_limits`, `.read`, `.read_with`, `.read_prefix`, `.validate` | no |
| `bencread.read_tree`, `.read_tree_with`, `.root`, `.node_count`, `.node` | no |
| `bencread.child`, `.node_at`, `.slice`, `.value_of`, `.span_at`, `.context` | no |
| `bencwrite.encoded_len`, `.write`, `.write_as_is`, `.canonical` | no |
| `bencwrite.is_canonical`, `.first_difference`, `.key_before` | no |
| `benctorrent.info_span`, `.info_hash_input` | no |
| `benctorrent.read`, `.from_value`, `.info_from_value`, `.to_value` | no |
| `benctorrent.total_length`, `.piece_count`, `.piece_hash`, `.piece_size`, `.files_in_piece` | no |
| `benctorrent.trackers`, `.is_trackerless`, `.is_safe_component` | no |
| `benctorrent.empty_info`, `.empty_torrent` | no |

## Licence

Apache-2.0. See `LICENSE`.

<!-- docs/writing-a-readme.md is the style guide for this page. -->
