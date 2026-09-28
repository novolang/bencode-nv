# Changelog

All notable changes to bencode-nv are recorded here. The format is
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
package follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
with the pre-1.0 rule that a breaking change bumps the MINOR number.

## [0.1.0] — 2026-09-28

The first implementation of the interface published as 0.0.1.

### Added

- `bencread` reads into an arena of nodes, each with its span, and
  `read` is that tree turned into values.  `validate` and `span_at`
  walk the bytes once without building anything and check every rule
  the tree reader checks, duplicate keys included.
- `bencwrite` writes with every dictionary sorted as raw bytes, or as
  it is; the sort keeps the order of equal keys.
- `benctorrent` reads single-file and multi-file torrents, checks every
  path component and the name, and answers the piece arithmetic.
- `tests/differential_tests.nv`, written by `tools/differential.py`,
  checks encodings, unsorted dictionaries and the info-hash bytes of
  twelve torrents against Python's bencode.py 4.1.0.
- `tests/bencedge_tests.nv` covers every refusal of both readers and a
  torrent with every member.

### Changed

These break code written against 0.0.x.

- `BencFault` has a new variant, `BencTooLarge(at, what, limit)`, for a
  byte string longer than `max_string_bytes` or more values than
  `max_values`.  The interface declared both limits and had no fault
  for them.
- A torrent's `name` is checked with `is_safe_component` like every
  path component, and a name that fails is `BencUnsafePath` with index
  `-1`.
- `benctorrent.files_in_piece` leaves out a file of length zero, which
  holds no piece's bytes.
- `bencread.value_of` answers the integer 0 for a number that is not a
  node, and `bencread.slice` an empty buffer.

## [0.0.1]

**The interface, published before anyone implements it.** Every public
type and function carries its full signature, its effect row and its
doc comment; every body is `todo()`; the release is recorded
`implemented = false`.

### Added

- `bencread` — the load-bearing interface, and it is TWO READERS. `read`
  answers the values; `read_tree` answers the same values in an arena
  whose every node carries the half-open byte range it occupied, and
  `slice` hands those exact bytes back. The second one has to exist
  because a torrent's info-hash is the SHA-1 of the `info` dictionary's
  ENCODED BYTES: re-encoding the values and hashing the result is right
  only when the file was written canonically, and files in the wild are
  not. A different hash is a different torrent, and the failure is
  silent — the client joins a swarm nobody is in and reports nothing
  wrong. `span_at` is the same answer in one scan with no tree, which
  is what a program that only wants an info-hash out of a large torrent
  should pay.
- `benctorrent.info_span` — the function the whole arrangement exists
  for, and the hash is NOT computed here: the caller hands the span's
  bytes to crypto-nv's `sha1`. So this package links no hash function,
  and BEP 52's version 2 torrents, whose info-hash is SHA-256 over the
  same span, need a different call at the caller's end and no change
  here.
- `bencwrite` — `write` sorts and `write_as_is` does not, and both are
  needed. Producing a new torrent means sorting, because BEP 3 says so.
  Reproducing a file somebody else wrote means not sorting, because its
  own order is what its info-hash was taken over. One function would
  have made the second job impossible, and that is the job that
  matters. `key_before` is the raw-byte comparison, exposed, because
  `"Z" < "a"` surprises everybody who expects a locale.
- `bencvalue` — a byte string is `Bytes` and not `Str`, because a
  torrent's `pieces` is a concatenation of SHA-1 digests and a package
  handing back text everywhere would truncate it at the first zero
  byte. A dictionary keeps the order it was read in, and `keys_sorted`
  is a QUESTION rather than a rule at the reader.
- The reader's two dictionary decisions, which look inconsistent and
  are not. An unsorted dictionary is accepted, because files in the
  wild are not always sorted and refusing one would refuse torrents
  every client accepts. A DUPLICATE key is refused, because an unsorted
  dictionary still has one value per key and a duplicated one does not
  — and for a torrent that means two readers agree on the hash and
  disagree on what it identifies.
- `benctorrent` — an unsafe path component is refused and not
  sanitised. `..` in a multi-file torrent's `path` is a stranger's
  request to write outside the download directory, and a caller handed
  a cleaned path would write where the torrent said, having been told
  nothing.
- `bencerror` — nineteen reasons, each with the byte offset it was
  found at, because bencode has no whitespace, no comments and no
  lines, so an offset is the only place a fault can be.

### Known

- `novo test` is red, and that is the release's expected state: every
  assertion in the API suite reaches `not implemented:
  bencode-nv.<module>.<fn>`.
- **The real-torrent corpus is named but not generated.** The suite
  carries BEP 3's own examples and the refusals bendy and bencodepy
  test; the run over a directory of real `.torrent` files, asserting
  that the SHA-1 of `info_span` is the info-hash the file is known by,
  lands with the implementation. It is the only test that catches a
  package that re-encodes when it should not.
- **BEP 52 version 2 torrents are not read.** Their merkle tree is a
  later release, and the span this package answers is the one they hash
  too.
- **No `tests/embedded_probe.nv`.** The absence is a claim not made
  rather than a claim skipped: the value tree is one allocation per
  node and a torrent's piece table is megabytes.
