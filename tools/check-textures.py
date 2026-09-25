"""Validate legacy PC MapGTA dictionaries; --fix normalizes eight known names.

Layout reference: CodeWalker.Core/GameFiles/Resources/Texture.cs in
https://github.com/dexyfex/CodeWalker. Only name bytes and dictionary hashes
change; the complete graphics segment (all mipmaps) remains byte-identical.
"""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import struct
import zlib

ROOT = Path(__file__).resolve().parents[1]
BASE_COMMIT = '594647dbcffec3df69518d59316df6dfa0351af3'
STYLES = ('classic', 'color', 'colorv2', 'default', 'postal', 'postalv2', 'postalvn', 'satellite', 'vietnam')
TILES = ('minimap_lod_128', *(f'minimap_sea_{row}_{col}' for row in range(3) for col in range(2)))
KNOWN_NAMES = {
    'postal_minimap_lod_128.ytd': 'minimap_sea_lod_128',
    'postalv2_minimap_lod_128.ytd': 'minimap_sea_lod_128',
    **{f'postalvn_minimap_sea_{row}_{col}.ytd': f'minimap_{row}_{col} (1)' for row in range(2) for col in range(2)},
    'postalvn_minimap_sea_2_0.ytd': 'minimap_2_0 (2)',
    'postalvn_minimap_sea_2_1.ytd': 'minimap_2_1',
}


def page_size(flags):
    fields = ((27, 1, 0), (26, 1, 1), (25, 1, 2), (24, 1, 3),
              (17, 127, 4), (11, 63, 5), (7, 15, 6), (5, 3, 7), (4, 1, 8))
    return (512 << (flags & 15)) * sum(((flags >> bit) & mask) << shift for bit, mask, shift in fields)


def joaat(name):
    value = 0
    for byte in name.lower().encode('ascii'):
        value = (value + byte) & 0xFFFFFFFF
        value = (value + (value << 10)) & 0xFFFFFFFF
        value ^= value >> 6
    value = (value + (value << 3)) & 0xFFFFFFFF
    value ^= value >> 11
    return (value + (value << 15)) & 0xFFFFFFFF


def inspect(raw):
    assert raw[:4] == b'RSC7' and len(raw) > 16, 'Expected RSC7'
    _, version, system, graphics = struct.unpack_from('<4I', raw)
    assert version == 13, 'Expected legacy PC YTD'
    data = zlib.decompress(raw[16:], -15)
    system_size = page_size(system)
    assert len(data) == system_size + page_size(graphics), 'Invalid page sizes'

    def address(pointer, size):
        assert pointer >> 28 == 5, 'Expected system pointer'
        offset = pointer & 0x0FFFFFFF
        assert offset + size <= system_size, 'Pointer out of range'
        return offset

    hashes, hash_count = struct.unpack_from('<QH', data, 0x20)
    textures, count = struct.unpack_from('<QH', data, 0x30)
    assert count == hash_count == 1, 'Only single-texture dictionaries supported'
    table = address(textures, 8)
    texture = address(struct.unpack_from('<Q', data, table)[0], 0x90)
    name_offset = address(struct.unpack_from('<Q', data, texture + 0x28)[0], 1)
    end = data.index(0, name_offset, system_size)
    name = data[name_offset:end].decode('ascii')
    hash_offset = address(hashes, 4)
    assert struct.unpack_from('<I', data, hash_offset)[0] == joaat(name), 'Name/hash mismatch'
    return data, system_size, name, name_offset, hash_offset, table, texture


def normalize(raw, expected, old_name):
    data, system_size, name, offset, hash_offset, table, texture = inspect(raw)
    if name == expected:
        return raw
    assert name == old_name, f'Unexpected name: {name!r}'
    replacement = expected.encode('ascii') + b'\0'
    # Existing names occupy 16-byte aligned allocations. Never relocate data.
    capacity = ((len(name) + 1 + 15) // 16) * 16
    assert len(replacement) <= capacity and offset % 16 == 0, 'Name allocation too small'
    size = max(len(name) + 1, len(replacement))
    assert offset + size <= system_size
    assert all(offset + size <= start or offset >= start + length
               for start, length in ((0, 64), (hash_offset, 4), (table, 8), (texture, 0x90)))
    assert all(byte in (0, 0xCD) for byte in data[offset + len(name) + 1:offset + size]), 'Non-padding bytes after name'
    updated = bytearray(data)
    updated[offset:offset + size] = replacement.ljust(size, b'\0')
    struct.pack_into('<I', updated, hash_offset, joaat(expected))
    assert updated[system_size:] == data[system_size:], 'Graphics data must not change'
    allowed = set(range(offset, offset + size)) | set(range(hash_offset, hash_offset + 4))
    assert all(a == b or index in allowed for index, (a, b) in enumerate(zip(data[:system_size], updated[:system_size])))
    compressor = zlib.compressobj(level=9, wbits=-15)
    result = raw[:16] + compressor.compress(updated) + compressor.flush()
    decoded, _, verified_name, *_ = inspect(result)
    assert decoded == updated and verified_name == expected
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fix', action='store_true', help='Back up and normalize known mismatches; write manifest')
    args = parser.parse_args()
    expected_files = {f'{style}_{tile}.ytd': tile for style in STYLES for tile in TILES}
    assert {path.name for path in ROOT.glob('*.ytd')} == set(expected_files), 'Missing or unexpected YTDs'
    planned, records = [], []
    for filename, expected in sorted(expected_files.items()):
        path = ROOT / filename
        original = path.read_bytes()
        raw = normalize(original, expected, KNOWN_NAMES.get(filename)) if args.fix else original
        data, system_size, name, *_ = inspect(raw)
        assert name == expected, f'{filename}: {name!r} != {expected!r}; run --fix'
        records.append({'file': filename, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                        'texture': name, 'graphics_sha256': hashlib.sha256(data[system_size:]).hexdigest()})
        if raw != original:
            planned.append((path, original, raw))
    # Finish validation before modifying any file. Original bytes stay outside Git.
    if planned:
        backup = ROOT.parent / ('MapGTA-backup-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
        backup.mkdir()
        for path, original, _ in planned:
            (backup / path.name).write_bytes(original)
        for path, _, raw in planned:
            temporary = path.with_suffix('.ytd.part')
            temporary.write_bytes(raw)
            temporary.replace(path)
        print(f'Backup: {backup}')
    manifest_path = ROOT / 'assets-manifest.json'
    manifest = {'upstream_commit': BASE_COMMIT, 'default_style': 'postalvn', 'assets': records}
    if args.fix:
        manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    else:
        assert json.loads(manifest_path.read_text(encoding='utf-8')) == manifest, 'Asset manifest is stale'
    print(f'PASS: {len(records)} textures; {len(planned)} normalized; name hashes, RSC7 pages and graphics verified.')


if __name__ == '__main__':
    main()
