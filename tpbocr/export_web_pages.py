# -*- coding: utf-8 -*-
"""Export high-performance, web-optimized page scans from JP2 zip to out/tpb_live_package/pages/.
Converts 1891 Boston edition JP2 pages to clean WebP/JPEG format resized to 1300x2121 or 2600x4242.
"""
import os, sys, io, zipfile, argparse
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BK = os.path.join(ROOT, "..", "tpb-data", "public-domain", "books",
                  "07_Allen_1891_New_American_Edition_Boston")
ZIP_PATH = os.path.join(BK, "therapeuticpocke0000timo_jp2.zip")
OUT_DIR = os.path.join(ROOT, "out", "tpb_live_package", "pages")
os.makedirs(OUT_DIR, exist_ok=True)

REF_WIDTH = 1300 # Standard web resolution; high dpi retina uses css 100%

def export_page(z, page_num, width=REF_WIDTH, quality=80):
    leaf = page_num + 6
    name = f"therapeuticpocke0000timo_jp2/therapeuticpocke0000timo_{leaf:04d}.jp2"
    if name not in z.namelist():
        print(f"Leaf {leaf} (p.{page_num}) not found in zip")
        return None

    out_webp = os.path.join(OUT_DIR, f"p{page_num:03d}.webp")
    out_jpg = os.path.join(OUT_DIR, f"p{page_num:03d}.jpg")

    if os.path.exists(out_webp) and os.path.exists(out_jpg):
        return os.path.getsize(out_webp) // 1024

    raw_bytes = z.read(name)
    im = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
    h = int(im.height * width / im.width)
    im_resized = im.resize((width, h), Image.LANCZOS)

    im_resized.save(out_webp, "WEBP", quality=quality)
    im_resized.save(out_jpg, "JPEG", quality=quality)

    sz_kb = os.path.getsize(out_webp) // 1024
    return sz_kb

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=17, help="Start page")
    ap.add_argument("--end", type=int, default=30, help="End page")
    ap.add_argument("--all", action="store_true", help="Export all 466 pages")
    args = ap.parse_args()

    if not os.path.exists(ZIP_PATH):
        print("Error: JP2 zip not found at:", ZIP_PATH)
        return

    z = zipfile.ZipFile(ZIP_PATH)
    start_p = 17
    end_p = 482 if args.all else args.end

    print(f"Exporting web-ready page scans from p.{start_p} to p.{end_p}...")
    count = 0
    total_kb = 0

    for p in range(start_p, end_p + 1):
        sz = export_page(z, p)
        if sz:
            count += 1
            total_kb += sz
            if count % 10 == 0 or count <= 5:
                print(f"  Exported p.{p:03d} ({sz} KB)")

    print(f"SUCCESS: Exported {count} pages to {OUT_DIR} (Avg {total_kb//max(1,count)} KB/page)")

if __name__ == "__main__":
    main()
