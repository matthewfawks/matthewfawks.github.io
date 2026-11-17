#!/usr/bin/env python3
"""Photo pipeline for matthewfawks.com.

Two commands:

  python3 tools/photos.py import <folder> --collection <slug> [--title "Title"]
      Resizes every JPEG/PNG/TIFF in <folder> for the web and adds it to the
      collection (creating the collection if needed):
        photos/<slug>/full/<slug>-NNN.jpg   long edge 2400 px, ~300-800 KB
        photos/<slug>/thumb/<slug>-NNN.jpg  long edge 800 px,  ~60-150 KB
      Colors are converted to sRGB, rotation is applied, and ALL metadata
      (including GPS location) is stripped. Files already imported (same
      source filename + size) are skipped, so re-running is safe.

  python3 tools/photos.py build
      Regenerates every gallery page (photography/<slug>/index.html) and the
      collections grid on photography/index.html from photos/collections.json.
      Warns about photos missing alt text or files.

Edit photos/collections.json by hand to reorder photos, set a collection's
cover, add alt text / captions, or add a "buy_url" to show a "Buy print" link.

Requires Pillow:  pip install Pillow
"""
import argparse
import html
import io
import json
import re
import sys
from pathlib import Path

try:
    from PIL import Image, ImageCms, ImageOps
except ImportError:
    sys.exit("Pillow is required:  pip install Pillow")

ROOT = Path(__file__).resolve().parent.parent
PHOTOS = ROOT / "photos"
MANIFEST = PHOTOS / "collections.json"
TEMPLATES = Path(__file__).resolve().parent / "templates"
LANDING = ROOT / "photography" / "index.html"

FULL_EDGE, FULL_Q = 2400, 80
THUMB_EDGE, THUMB_Q = 800, 75
EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}
SRGB = ImageCms.createProfile("sRGB")


def load():
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text())
    return {"collections": []}


def save(data):
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def to_srgb(im):
    icc = im.info.get("icc_profile")
    if icc:
        try:
            src = ImageCms.ImageCmsProfile(io.BytesIO(icc))
            im = ImageCms.profileToProfile(im, src, SRGB, outputMode="RGB")
        except Exception:
            pass
    return im.convert("RGB")


def save_jpeg(im, path, edge, quality):
    im = im.copy()
    im.thumbnail((edge, edge), Image.LANCZOS)  # never upscales
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, "JPEG", quality=quality, optimize=True, progressive=True)  # no exif passed = stripped
    return im.size


def cmd_import(args):
    src = Path(args.folder).expanduser()
    if not src.is_dir():
        sys.exit(f"Not a folder: {src}")
    slug = slugify(args.collection)
    data = load()
    col = next((c for c in data["collections"] if c["slug"] == slug), None)
    if col is None:
        col = {"slug": slug, "title": args.title or args.collection.replace("-", " ").title(),
               "description": "", "cover": "", "photos": []}
        data["collections"].append(col)
    elif args.title:
        col["title"] = args.title
    seen = {(p.get("source"), p.get("source_bytes")) for p in col["photos"]}
    n = max([int(re.search(r"-(\d+)\.jpg$", p["file"]).group(1)) for p in col["photos"]] or [0])
    added = 0
    for f in sorted(p for p in src.iterdir() if p.suffix.lower() in EXTS):
        key = (f.name, f.stat().st_size)
        if key in seen:
            continue
        n += 1
        name = f"{slug}-{n:03d}.jpg"
        im = to_srgb(ImageOps.exif_transpose(Image.open(f)))
        w, h = save_jpeg(im, PHOTOS / slug / "full" / name, FULL_EDGE, FULL_Q)
        save_jpeg(im, PHOTOS / slug / "thumb" / name, THUMB_EDGE, THUMB_Q)
        col["photos"].append({"file": name, "w": w, "h": h, "alt": "", "caption": "",
                              "buy_url": "", "source": f.name, "source_bytes": f.stat().st_size})
        added += 1
        kb = (PHOTOS / slug / "full" / name).stat().st_size // 1024
        print(f"  {f.name} -> {name}  {w}x{h}  {kb} KB")
    if not col["cover"] and col["photos"]:
        col["cover"] = col["photos"][0]["file"]
    if not col["photos"]:
        # nothing was imported into a brand-new collection: don't leave an empty entry behind
        data["collections"].remove(col)
        print(f"No images found in {src}; nothing imported.")
        return
    save(data)
    print(f"Imported {added} photo(s) into '{slug}'. Now run:  python3 tools/photos.py build")


def esc(s):
    return html.escape(s or "", quote=True)


def gallery_items(col):
    out = []
    for i, p in enumerate(col["photos"], 1):
        alt = p.get("alt") or f"{col['title']}, photo {i}"
        base = f"/photos/{col['slug']}"
        buy = (f' data-buy="{esc(p["buy_url"])}"' if p.get("buy_url") else "")
        cap = f' data-caption="{esc(p["caption"])}"' if p.get("caption") else ""
        out.append(
            f'      <a class="g-item" href="{base}/full/{p["file"]}"{cap}{buy}>'
            f'<img src="{base}/thumb/{p["file"]}" alt="{esc(alt)}" width="{p["w"]}" height="{p["h"]}" loading="lazy" decoding="async"></a>'
        )
    return "\n".join(out)


def collection_cards(data):
    out = []
    for c in data["collections"]:
        if not c["photos"]:
            continue
        cover = c.get("cover") or c["photos"][0]["file"]
        cp = next((p for p in c["photos"] if p["file"] == cover), c["photos"][0])
        alt = cp.get("alt") or f"Cover photo for {c['title']}"
        out.append(
            f'      <a class="c-card" href="/photography/{c["slug"]}/">\n'
            f'        <img src="/photos/{c["slug"]}/thumb/{cover}" alt="{esc(alt)}" loading="lazy" decoding="async">\n'
            f'        <span class="c-meta"><span class="c-title">{esc(c["title"])}</span><span class="c-count">{len(c["photos"])}</span></span>\n'
            f'      </a>'
        )
    return "\n".join(out)


def replace_between(text, name, new):
    pat = re.compile(rf"(<!-- {name}:START -->)(.*?)(<!-- {name}:END -->)", re.S)
    if not pat.search(text):
        sys.exit(f"Markers <!-- {name}:START/END --> not found in photography/index.html")
    return pat.sub(lambda m: m.group(1) + "\n" + new + "\n      " + m.group(3), text)


def cmd_build(_args):
    data = load()
    tpl = (TEMPLATES / "gallery.html").read_text()
    warnings = []
    total = 0
    for c in data["collections"]:
        if not c["photos"]:
            continue  # empty collections get no page and no card
        for p in c["photos"]:
            if not (PHOTOS / c["slug"] / "full" / p["file"]).exists():
                warnings.append(f"missing file: photos/{c['slug']}/full/{p['file']}")
            if not p.get("alt"):
                warnings.append(f"no alt text: {c['slug']}/{p['file']}")
        total += len(c["photos"])
        page = (tpl.replace("{{TITLE}}", esc(c["title"]))
                   .replace("{{DESCRIPTION}}", esc(c.get("description") or f"{len(c['photos'])} photographs"))
                   .replace("{{COUNT}}", str(len(c["photos"])))
                   .replace("{{OG_IMAGE}}", f"/photos/{c['slug']}/full/{c.get('cover') or c['photos'][0]['file']}" if c["photos"] else "")
                   .replace("{{ITEMS}}", gallery_items(c)))
        out = ROOT / "photography" / c["slug"] / "index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(page)
        print(f"  built photography/{c['slug']}/  ({len(c['photos'])} photos)")
    text = LANDING.read_text()
    text = replace_between(text, "COLLECTIONS", collection_cards(data))
    n = len([c for c in data["collections"] if c["photos"]])
    text = replace_between(text, "COUNT", f"      {total} photographs across {n} collections")
    LANDING.write_text(text)
    print(f"Updated photography/index.html ({n} collections, {total} photos)")
    if warnings:
        alt_missing = sum(1 for w in warnings if w.startswith("no alt"))
        other = [w for w in warnings if not w.startswith("no alt")]
        for w in other:
            print("  WARNING:", w)
        if alt_missing:
            print(f"  note: {alt_missing} photo(s) have no alt text yet (a generic one is used).")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("import", help="resize a folder of exports into a collection")
    i.add_argument("folder")
    i.add_argument("--collection", required=True)
    i.add_argument("--title")
    i.set_defaults(func=cmd_import)
    b = sub.add_parser("build", help="regenerate gallery pages")
    b.set_defaults(func=cmd_build)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
