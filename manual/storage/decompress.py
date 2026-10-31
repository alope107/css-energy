import zstandard as zstd

if __name__ == "__main__":
    with open("site/cells/references/1.png", 'rb') as f:
        dictionary = f.read()
    with open("site/cells/probes/1.png", 'rb') as f:
        compressed = f.read()
        # Hash checking would go here by checking first 8 bytes for magic
        # And next 32 for hash match
        # for now we just skip the first frame
        compressed = compressed[40:]

    print(dictionary)
    print(compressed)

    zstd_dict = zstd.ZstdCompressionDict(dictionary, dict_type=zstd.DICT_TYPE_RAWCONTENT)
    decompressor = zstd.ZstdDecompressor(zstd_dict)

    try:
        decompressed = decompressor.decompress(compressed)
        with open("decompressed.png", "wb") as f:
            f.write(decompressed)
    except zstd.ZstdError as e:
        print(e)