"""
Compress edgar_cache directory to a single tarball for git commit.

JSON files compress extremely well. Expected: 2 GB → ~300-400 MB.

Usage:
    python compress_edgar_cache.py
"""

import os
import sys
import tarfile
import time

CACHE_DIR = "edgar_cache"
OUTPUT = "edgar_cache.tar.gz"


def main():
    if not os.path.exists(CACHE_DIR):
        print(f"ERROR: {CACHE_DIR} directory not found")
        sys.exit(1)

    print(f"Compressing {CACHE_DIR} to {OUTPUT}...")

    file_count = sum(1 for f in os.listdir(CACHE_DIR) if f.endswith(".json"))
    raw_size = sum(
        os.path.getsize(os.path.join(CACHE_DIR, f))
        for f in os.listdir(CACHE_DIR)
        if os.path.isfile(os.path.join(CACHE_DIR, f))
    )
    print(f"Source: {file_count} JSON files, {raw_size / (1024*1024):.1f} MB raw")

    start = time.time()

    with tarfile.open(OUTPUT, "w:gz", compresslevel=9) as tar:
        tar.add(CACHE_DIR, arcname=CACHE_DIR)

    elapsed = time.time() - start
    final_size = os.path.getsize(OUTPUT) / (1024 * 1024)

    print(f"Done in {elapsed:.1f}s")
    print(f"Compressed: {final_size:.1f} MB")
    print(f"Compression ratio: {raw_size / (1024*1024) / final_size:.1f}x")

    if final_size < 100:
        print("\n✓ Under 100 MB - safe to commit")
    elif final_size < 500:
        print("\n⚠ Over 100 MB - GitHub will warn but accept")
    elif final_size < 2000:
        print("\n⚠ Large file - push may be slow but should work")
    else:
        print("\n✗ Over 2 GB - exceeds GitHub limits, need git-lfs")

    print(f"\nNext steps:")
    print(f"1. git add {OUTPUT}")
    print(f"2. git commit -m 'chore: compressed EDGAR cache for fast workflow runs'")
    print(f"3. git push")


if __name__ == "__main__":
    main()
