#!/usr/bin/env python3
"""Photo pipeline for matthewfawks.com.

Commands (each one rebuilds the pages when it is done):

  python3 tools/photos.py import <folder> --collection <slug> [--title "Title"]
      Resizes every JPEG/PNG/TIFF in <folder> for the web and adds it to the
      collection (creating the collection if needed):
        photos/<slug>/full/<slug>-NNN.jpg   long edge 2400 px, ~300-800 KB
        photos/<slug>/thumb/<slug>-NNN.jpg  long edge 800 px,  ~60-150 KB
      Colors are converted to sRGB, rotation is applied, and ALL metadata
      (including GPS location) is stripped. Files already imported (same
      source filename + size) are skipped, so re-running is safe; a re-export
      with the same filename but a different size (e.g. after fixing its
      location in Lightroom) replaces the photo in place.

  python3 tools/photos.py list [<slug>]
      Shows each photo's site name, Lightroom number and location.

  python3 tools/photos.py cover <slug> <photo>
      Makes <photo> the cover of collection <slug>.

  python3 tools/photos.py remove <photo> [<photo> ...]
      Takes photos off the site (deletes their entry and both image files).

  python3 tools/photos.py sync <folder>
      <folder> holds one folder per collection (landscapes, cityscapes, ...). Photos
      no longer in their collection's folder come off the site; new and re-exported
      ones are imported. Moving a file between folders moves the photo. Folders
      starting with _ or ~ (e.g. _removed) are ignored.

  python3 tools/photos.py build
      Regenerates every gallery page (photography/<slug>/index.html) and the
      collections grid on photography/index.html from photos/collections.json.
      Only needed after editing collections.json by hand.

A <photo> is either its site name (landscapes-021) or its Lightroom export number
(158, from FPTS-20261123-158.jpg).

Location (Lightroom's Sublocation, City, State/Province and Country fields) and the
camera, lens, focal length, aperture, shutter speed and ISO are read from each export
and shown on the photo; the published files keep no metadata, GPS included.

Photos appear in Lightroom file-name order (import and sync keep them sorted).
Edit photos/collections.json by hand to set a collection's
cover, fix a location or caption, add alt text, add a "buy_url" to show a
"Buy print" link, set a collection's "layout" to "wide" (one photo per row,
used for panoramas), or set what the line under a gallery's title lists:
"places_by": "city" (cities instead of states/countries) or "places": "your own text".
A collection's "cover_focus" (e.g. "35% 50%", left-right then top-bottom) moves the
crop of its cover on the collections grid.

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


def thumb_edge(w, h):
    """800 px long edge, except very wide panoramas keep a 600 px short edge so they
    stay sharp when shown full width or cropped into a collection card."""
    ratio = max(w, h) / min(w, h)
    return THUMB_EDGE if ratio <= 2 else min(FULL_EDGE, round(600 * ratio))


def _xmp_field(xmp, tag):
    """Read a simple XMP field written either as an attribute or as an element."""
    m = re.search(rf'{tag}="([^"]*)"', xmp) or re.search(rf"<{tag}>([^<]*)</{tag}>", xmp)
    if not m:  # dc:title / dc:description are language alternatives: <dc:title><rdf:Alt><rdf:li ...>text
        m = re.search(rf"<{tag}>\s*<rdf:Alt>\s*<rdf:li[^>]*>([^<]*)</rdf:li>", xmp)
    return html.unescape(m.group(1)).strip() if m else ""


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def format_location(place="", city="", state="", country=""):
    """'Alcatraz Island' + San Francisco + CA + United States -> 'Alcatraz Island, San Francisco, CA, United States'.
    Lightroom's Location (sublocation) field often repeats the city ('Dallas, TX'), so only its first
    part is kept, and any part already present is dropped ('Dallas, TX, Dallas, TX' -> 'Dallas, TX')."""
    first = place.split(",")[0].strip() if city else place
    parts, seen = [], set()
    for part in (first, city, state, country):
        for bit in (b.strip() for b in part.split(",")):
            if bit and bit.lower() not in seen:
                parts.append(bit)
                seen.add(bit.lower())
    return ", ".join(parts)


def read_meta(im):
    """Location text and a camera/exposure line from an export's EXIF, XMP and IPTC.
    Only these text values are kept; GPS coordinates are never read or published."""
    exif = im.getexif()
    sub = exif.get_ifd(0x8769)
    xmp = im.info.get("xmp") or im.info.get("XML:com.adobe.xmp") or b""
    if isinstance(xmp, bytes):
        xmp = xmp.decode("utf-8", "ignore")
    loc = {k: _xmp_field(xmp, t) for k, t in (("place", "Iptc4xmpCore:Location"), ("city", "photoshop:City"),
                                               ("state", "photoshop:State"), ("country", "photoshop:Country"))}
    if not any(loc.values()):
        try:
            from PIL import IptcImagePlugin
            iptc = IptcImagePlugin.getiptcinfo(im) or {}
            def g(k):
                v = iptc.get(k)
                v = v[0] if isinstance(v, list) else v
                return v.decode("utf-8", "ignore").strip() if v else ""
            loc = {"place": g((2, 92)), "city": g((2, 90)), "state": g((2, 95)), "country": g((2, 101))}
        except Exception:
            pass
    location = format_location(**loc)

    model = (exif.get(272) or "").strip()
    make = (exif.get(271) or "").strip()
    camera = model if not make or model.lower().startswith(make.split()[0].lower()) else f"{make} {model}"
    camera = camera.replace("Canon Canon", "Canon")
    lens = (sub.get(0xA434) or "").strip()
    if lens.lower().startswith("canon "):
        lens = lens[6:]  # 'Canon RF24-105mm ...' and 'RF24-105mm ...' are the same lens
    bits = []
    focal, iso = _num(sub.get(0x920A)), sub.get(0x8827)
    shutter, aperture = _num(sub.get(0x829A)), _num(sub.get(0x829D))
    if focal:
        bits.append(f"{focal:g}mm")
    if aperture:
        bits.append(f"f/{aperture:g}")
    if shutter:
        bits.append(f"1/{round(1 / shutter)}s" if shutter < 0.5 else f"{shutter:g}s")
    if iso:
        bits.append(f"ISO {iso[0] if isinstance(iso, tuple) else iso}")
    gear = " + ".join(x for x in (camera, lens) if x)
    exposure = " · ".join(([gear] if gear else []) + bits)
    return {
        "location": location,
        "exif": exposure,
        "title": _xmp_field(xmp, "dc:title"),
        "description": _xmp_field(xmp, "dc:description"),
        "taken": (sub.get(0x9003) or "")[:10].replace(":", "-"),
    }


def cmd_import(args):
    src = Path(args.folder).expanduser()
    if not src.is_dir():
        sys.exit(f"Not a folder: {src}")
    data = load()
    added, updated, slug = import_folder(data, src, args.collection, args.title)
    if added is None:
        print(f"No images found in {src}; nothing imported.")
        return
    save(data)
    print(f"Imported {added} new and updated {updated} photo(s) in '{slug}'.")
    cmd_build(args)


def import_folder(data, src, collection, title=None):
    """Add new photos from src to the collection and replace re-exported ones.
    Returns (added, updated, slug); added is None when a new collection got no photos."""
    slug = slugify(collection)
    col = next((c for c in data["collections"] if c["slug"] == slug), None)
    if col is None:
        col = {"slug": slug, "title": title or collection.replace("-", " ").title(),
               "description": "", "cover": "", "photos": []}
        data["collections"].append(col)
    elif title:
        col["title"] = title
    by_source = {p.get("source"): p for p in col["photos"]}
    n = max([int(re.search(r"-(\d+)\.jpg$", p["file"]).group(1)) for p in col["photos"]] or [0])
    added = updated = 0
    for f in sorted(p for p in src.iterdir() if p.suffix.lower() in EXTS):
        size = f.stat().st_size
        old = by_source.get(f.name)
        if old and old.get("source_bytes") == size:
            continue  # already imported, unchanged
        raw = Image.open(f)
        meta = read_meta(raw)
        im = to_srgb(ImageOps.exif_transpose(raw))
        if old:
            # re-export of a photo already on the site (e.g. fixed metadata): replace it in
            # place, keeping its file name, position, tags and buy link
            name = old["file"]
        else:
            n += 1
            name = f"{slug}-{n:03d}.jpg"
        w, h = save_jpeg(im, PHOTOS / slug / "full" / name, FULL_EDGE, FULL_Q)
        save_jpeg(im, PHOTOS / slug / "thumb" / name, thumb_edge(w, h), THUMB_Q)
        fresh = {"w": w, "h": h, "alt": meta["description"] or meta["title"], "caption": meta["title"],
                 "location": meta["location"], "exif": meta["exif"], "taken": meta["taken"],
                 "source": f.name, "source_bytes": size}
        if old:
            old.update(fresh)
            updated += 1
        else:
            col["photos"].append({"file": name, **fresh, "tags": [], "buy_url": ""})
            added += 1
        kb = (PHOTOS / slug / "full" / name).stat().st_size // 1024
        print(f"  {f.name} -> {name}  {w}x{h}  {kb} KB  {meta['location'] or '(no location)'}"
              + ("  (updated)" if old else ""))
    col["photos"].sort(key=lambda p: p.get("source", ""))  # galleries follow Lightroom file order
    if not col["cover"] and col["photos"]:
        col["cover"] = col["photos"][0]["file"]
    if not col["photos"]:
        # nothing was imported into a brand-new collection: don't leave an empty entry behind
        data["collections"].remove(col)
        return None, 0, slug
    return added, updated, slug


def esc(s):
    return html.escape(s or "", quote=True)


def gallery_items(col):
    out = []
    for i, p in enumerate(col["photos"], 1):
        alt = p.get("alt") or (f"{col['title']} photograph, {p['location']}" if p.get("location")
                               else f"{col['title']}, photo {i}")
        base = f"/photos/{col['slug']}"
        buy = (f' data-buy="{esc(p["buy_url"])}"' if p.get("buy_url") else "")
        cap = f' data-caption="{esc(p["caption"])}"' if p.get("caption") else ""
        loc = f' data-location="{esc(p["location"])}"' if p.get("location") else ""
        exf = f' data-exif="{esc(p["exif"])}"' if p.get("exif") else ""
        overlay = ""
        if p.get("location") or p.get("exif"):
            overlay = ('<span class="g-meta">'
                       + (f'<span class="g-loc">{esc(p["location"])}</span>' if p.get("location") else "")
                       + (f'<span class="g-exif">{esc(p["exif"])}</span>' if p.get("exif") else "")
                       + "</span>")
        out.append(
            f'      <a class="g-item" style="--r:{p["w"] / p["h"]:.3f}" href="{base}/full/{p["file"]}"{cap}{loc}{exf}{buy}>'
            f'<img src="{base}/thumb/{p["file"]}" alt="{esc(alt)}" width="{p["w"]}" height="{p["h"]}" loading="lazy" decoding="async">{overlay}</a>'
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
            f'        <img src="/photos/{c["slug"]}/thumb/{cover}" alt="{esc(alt)}" loading="lazy" decoding="async"'
            + (f' style="object-position: {esc(c["cover_focus"])}"' if c.get("cover_focus") else "") + '>\n'
            f'        <span class="c-meta"><span class="c-title">{esc(c["title"])}</span><span class="c-count">{len(c["photos"])}</span></span>\n'
            f'      </a>'
        )
    return "\n".join(out)


def replace_between(text, name, new):
    pat = re.compile(rf"(<!-- {name}:START -->)(.*?)(<!-- {name}:END -->)", re.S)
    if not pat.search(text):
        sys.exit(f"Markers <!-- {name}:START/END --> not found in photography/index.html")
    return pat.sub(lambda m: m.group(1) + "\n" + new + "\n      " + m.group(3), text)


US_STATES = dict(x.replace("_", " ").split("=") for x in (
    "AL=Alabama AK=Alaska AZ=Arizona AR=Arkansas CA=California CO=Colorado CT=Connecticut DE=Delaware "
    "DC=Washington,_DC FL=Florida GA=Georgia HI=Hawaii ID=Idaho IL=Illinois IN=Indiana IA=Iowa KS=Kansas "
    "KY=Kentucky LA=Louisiana ME=Maine MD=Maryland MA=Massachusetts MI=Michigan MN=Minnesota "
    "MS=Mississippi MO=Missouri MT=Montana NE=Nebraska NV=Nevada NH=New_Hampshire NJ=New_Jersey "
    "NM=New_Mexico NY=New_York NC=North_Carolina ND=North_Dakota OH=Ohio OK=Oklahoma OR=Oregon "
    "PA=Pennsylvania RI=Rhode_Island SC=South_Carolina SD=South_Dakota TN=Tennessee TX=Texas UT=Utah "
    "VT=Vermont VA=Virginia WA=Washington WV=West_Virginia WI=Wisconsin WY=Wyoming").split())


def place_of(location, by="region"):
    """'Navy Pier, Chicago, IL, United States' -> 'Illinois' (region) or 'Chicago' (city)."""
    parts = [x.strip() for x in location.split(",") if x.strip()]
    if not parts:
        return ""
    us = parts[-1] == "United States"
    if by == "city" and len(parts) >= (3 if us else 2):
        return parts[-3] if us else parts[-2]
    if us and len(parts) >= 2:
        return US_STATES.get(parts[-2], parts[-2])
    return parts[-1]


def places_line(c, limit=7):
    """The line under a gallery's title: where the photos were taken, most first, and the years."""
    if c.get("places"):
        return c["places"]  # written by hand in collections.json
    counts = {}
    for p in c["photos"]:
        place = place_of(p.get("location", ""), c.get("places_by", "region"))
        if place:
            counts[place] = counts.get(place, 0) + 1
    names = sorted(counts, key=lambda k: (-counts[k], k))
    text = ", ".join(names[:limit]) + (" and more" if len(names) > limit else "")
    years = sorted(p["taken"][:4] for p in c["photos"] if p.get("taken"))
    if years:
        text += (" · " if text else "") + (years[0] if years[0] == years[-1] else f"{years[0]}–{years[-1]}")
    return text


def find_photo(data, ref, slug=None):
    """Find a photo by site name (landscapes-021[.jpg]) or Lightroom export number (158)."""
    ref = ref.strip().removesuffix(".jpg")
    hits = []
    for c in data["collections"]:
        if slug and c["slug"] != slug:
            continue
        for p in c["photos"]:
            num = re.search(r"(\d+)\.\w+$", p.get("source", ""))
            if p["file"].removesuffix(".jpg") == ref or (ref.isdigit() and num and int(num.group(1)) == int(ref)):
                hits.append((c, p))
    if not hits:
        sys.exit(f"No photo matches '{ref}'" + (f" in '{slug}'" if slug else "") + ". Try:  python3 tools/photos.py list")
    if len(hits) > 1:
        sys.exit(f"'{ref}' matches more than one photo: " + ", ".join(p["file"] for _, p in hits)
                 + ". Use the site name instead.")
    return hits[0]


def cmd_list(args):
    for c in load()["collections"]:
        if args.collection and c["slug"] != slugify(args.collection):
            continue
        print(f"{c['title']} ({c['slug']}, {len(c['photos'])} photos, cover {c.get('cover', '')})")
        for p in c["photos"]:
            num = re.search(r"(\d+)\.\w+$", p.get("source", ""))
            print(f"  {p['file'].removesuffix('.jpg'):<28} {num.group(1) if num else '':>5}  {p.get('location', '')}")


def cmd_cover(args):
    data = load()
    slug = slugify(args.collection)
    if not any(c["slug"] == slug for c in data["collections"]):
        sys.exit(f"No collection '{slug}'. Collections: " + ", ".join(c["slug"] for c in data["collections"]))
    col, p = find_photo(data, args.photo, slug)
    col["cover"] = p["file"]
    save(data)
    print(f"Cover of '{slug}' is now {p['file']} ({p.get('location', '')})")
    cmd_build(args)


def remove_photo(col, p):
    col["photos"].remove(p)
    for kind in ("full", "thumb"):
        (PHOTOS / col["slug"] / kind / p["file"]).unlink(missing_ok=True)
    print(f"Removed {p['file']} ({p.get('source', '')}) from '{col['slug']}'")
    if col.get("cover") == p["file"]:
        col["cover"] = col["photos"][0]["file"] if col["photos"] else ""
        print(f"  note: that was the cover of '{col['slug']}'; the cover is now {col['cover'] or 'empty'}")


def cmd_remove(args):
    data = load()
    for ref in args.photos:
        remove_photo(*find_photo(data, ref))
    save(data)
    cmd_build(args)


def cmd_sync(args):
    """Make the site match a folder of theme folders: photos no longer in a collection's
    folder come off the site, new or re-exported ones go on. Folders starting with _ or ~
    are ignored, so a _removed folder is a safe place to park photos."""
    root = Path(args.folder).expanduser()
    if not root.is_dir():
        sys.exit(f"Not a folder: {root}")
    folders = {slugify(d.name): d for d in sorted(root.iterdir())
               if d.is_dir() and not d.name.startswith(("_", "~", "."))}
    data = load()
    for col in data["collections"]:
        if col["slug"] not in folders:
            print(f"  note: no '{col['slug']}' folder in {root}; left as is")
            continue
        present = {f.name for f in folders[col["slug"]].iterdir() if f.suffix.lower() in EXTS}
        for p in [p for p in col["photos"] if p.get("source") not in present]:
            remove_photo(col, p)
    data["collections"] = [c for c in data["collections"] if c["photos"] or c["slug"] not in folders]
    for slug, folder in folders.items():
        added, updated, _ = import_folder(data, folder, slug)
        if added:
            print(f"Added {added} photo(s) to '{slug}'")
        if updated:
            print(f"Updated {updated} re-exported photo(s) in '{slug}'")
    save(data)
    cmd_build(args)


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
            if not p.get("alt") and not p.get("location"):
                warnings.append(f"no alt text: {c['slug']}/{p['file']}")
        total += len(c["photos"])
        page = (tpl.replace("{{TITLE}}", esc(c["title"]))
                   .replace("{{DESCRIPTION}}", esc(c.get("description") or f"{len(c['photos'])} photographs"))
                   .replace("{{COUNT}}", str(len(c["photos"])))
                   .replace("{{PLACES}}", esc(places_line(c)))
                   .replace("{{OG_IMAGE}}", f"/photos/{c['slug']}/full/{c.get('cover') or c['photos'][0]['file']}" if c["photos"] else "")
                   .replace("{{GRID_CLASS}}", "g-grid wide" if c.get("layout") == "wide" else "g-grid")
                   .replace("{{ITEMS}}", gallery_items(c)))
        out = ROOT / "photography" / c["slug"] / "index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(page)
        print(f"  built photography/{c['slug']}/  ({len(c['photos'])} photos)")
    text = LANDING.read_text()
    text = replace_between(text, "COLLECTIONS", collection_cards(data))
    n = len([c for c in data["collections"] if c["photos"]])
    if "<!-- COUNT:START -->" in text:  # optional "N photographs across N collections" line
        text = replace_between(text, "COUNT", f"      {total} photographs across {n} collections")
    LANDING.write_text(text)
    print(f"Updated photography/index.html ({n} collections, {total} photos)")
    if warnings:
        alt_missing = sum(1 for w in warnings if w.startswith("no alt"))
        other = [w for w in warnings if not w.startswith("no alt")]
        for w in other:
            print("  WARNING:", w)
        if alt_missing:
            print(f"  note: {alt_missing} photo(s) have no alt text or location (a generic alt text is used).")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("import", help="resize a folder of exports into a collection")
    i.add_argument("folder")
    i.add_argument("--collection", required=True)
    i.add_argument("--title")
    i.set_defaults(func=cmd_import)
    li = sub.add_parser("list", help="show photos with their Lightroom numbers")
    li.add_argument("collection", nargs="?")
    li.set_defaults(func=cmd_list)
    cv = sub.add_parser("cover", help="set a collection's cover photo")
    cv.add_argument("collection")
    cv.add_argument("photo")
    cv.set_defaults(func=cmd_cover)
    sy = sub.add_parser("sync", help="make the site match a folder of theme folders")
    sy.add_argument("folder")
    sy.set_defaults(func=cmd_sync)
    rm = sub.add_parser("remove", help="take photos off the site")
    rm.add_argument("photos", nargs="+")
    rm.set_defaults(func=cmd_remove)
    b = sub.add_parser("build", help="regenerate gallery pages")
    b.set_defaults(func=cmd_build)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
