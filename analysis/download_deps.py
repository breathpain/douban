#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""下载 jQuery 和 DataTables，用于内嵌到 dashboard 中"""

import urllib.request
import os

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# bootcdn 上 DataTables 的路径和 cdnjs 不同，尝试多个源
files = [
    ("jquery.min.js", "https://cdn.bootcdn.net/ajax/libs/jquery/3.7.0/jquery.min.js"),
    ("datatables.min.js", "https://cdnjs.cloudflare.com/ajax/libs/datatables/1.10.21/js/jquery.dataTables.min.js"),
    ("datatables.min.css", "https://cdnjs.cloudflare.com/ajax/libs/datatables/1.10.21/css/jquery.dataTables.min.css"),
]

for filename, url in files:
    filepath = os.path.join(OUTPUT_DIR, filename)
    print(f"Downloading {filename}...")
    try:
        data = urllib.request.urlopen(url, timeout=30).read()
        with open(filepath, "wb") as f:
            f.write(data)
        print(f"  ✅ {len(data):,d} bytes -> {filepath}")
    except Exception as e:
        print(f"  ❌ Failed: {e}")

print("\nDone.")
