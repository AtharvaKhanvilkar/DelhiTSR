import sys
sys.path.insert(0, r"c:\Users\Heramb Khanvilkar\Desktop\tsr-engine")
from scratch.doc_texts_part1 import DOC_01_TEXT, DOC_02_TEXT

lines1 = DOC_01_TEXT.strip().splitlines()
lines2 = DOC_02_TEXT.strip().splitlines()
print(f"DOC_01_TEXT: {len(lines1)} lines")
print(f"DOC_02_TEXT: {len(lines2)} lines")

for kw in ["DDA", "Delhi Development Authority", "allotment", "residential"]:
    count = DOC_01_TEXT.lower().count(kw.lower())
    print(f"  DOC01 '{kw}': {count} occurrences")

for kw in ["residential", "flat", "fourth floor", "DDA allotment"]:
    count = DOC_02_TEXT.lower().count(kw.lower())
    print(f"  DOC02 '{kw}': {count} occurrences")
