"""Recompress prices_cache.parquet with zstd to reduce size."""
import os
import pandas as pd

print("Loading current parquet...")
df = pd.read_parquet("prices_cache.parquet")
print(f"Loaded {len(df):,} rows")

old_size = os.path.getsize("prices_cache.parquet") / (1024 * 1024)
print(f"Current size: {old_size:.1f} MB")

print("\nRecompressing with zstd level 15...")
df.to_parquet("prices_cache.parquet", compression="zstd", compression_level=15, index=False)

new_size = os.path.getsize("prices_cache.parquet") / (1024 * 1024)
print(f"New size: {new_size:.1f} MB")
print(f"Savings: {old_size - new_size:.1f} MB ({(1 - new_size/old_size)*100:.0f}%)")

if new_size < 100:
    print("\n✓ Under 100 MB - safe to commit and push")
else:
    print(f"\n✗ Still over 100 MB by {new_size - 100:.1f} MB - need to split file")
