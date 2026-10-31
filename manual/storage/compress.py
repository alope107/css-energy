import zstandard as zstd
import hashlib
from pathlib import Path


# dcz compressed data needs a hash of the reference data at the front to
# match it against the stored reference data
# the hash is held in a skippable frame, so zstd ignores it, only the browser
# uses it
def dcz_header(reference_data):
    skippable_frame_magic = b"\x5e\x2a\x4d\x18"
    hash_size = b"\x20\x00\x00\x00" # x20 = 32 bytes
    dict_hash = hashlib.sha256(reference_data).digest()
    return skippable_frame_magic + hash_size + dict_hash

# compresses new data against reference using dictionary compressed zstd
def dcz_compress(reference_data, new_data):
    zd = zstd.ZstdCompressionDict(reference_data, dict_type=zstd.DICT_TYPE_RAWCONTENT)
    return (dcz_header(reference_data)
            + zstd.ZstdCompressor(dict_data=zd).compress(new_data))

def make_probes(reference_dir: Path, probe_dir: Path):
    for reference_file in reference_dir.iterdir():
        if reference_file.is_file():
            with open(reference_file, "rb") as f:
                reference_data = f.read()
            probe_file = probe_dir / reference_file.name
            with open(probe_file, "wb") as f:
                f.write(dcz_compress(reference_data, reference_data))

if __name__ == "__main__":
    make_probes(Path("site/cells/references"), Path("site/cells/probes"))
            