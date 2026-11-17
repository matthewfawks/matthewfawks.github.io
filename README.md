# matthewfawks.com

Personal site of Matthew Fawks. Plain HTML/CSS, served by GitHub Pages from the `master` branch (no Jekyll; see `.nojekyll`).

## Layout

| Path | What it is |
|---|---|
| `index.html` | Résumé home page |
| `documents/matthew-fawks-resume.pdf` | Résumé PDF linked from the home page (replace the file to update it) |
| `photography/index.html` | Photography landing page (hero, collections, prints, about) |
| `photography/<collection>/index.html` | Gallery pages. **Generated**; don't edit by hand |
| `photos/<collection>/full/`, `thumb/` | Web-sized photos (2400 px / 800 px, metadata stripped) |
| `photos/collections.json` | Order, titles, covers, alt text, captions and print links for every photo |
| `tools/photos.py` | Photo import + gallery build script |
| `assets/` | CSS, JS (gallery lightbox), headshot, favicon |
| `collection-*.html` | Redirects from the old site's gallery URLs |

## Adding photos

1. Export from Lightroom: JPEG, sRGB, long edge 2400 px, quality 75–80, metadata "Copyright & Contact Info Only" (no location). One folder per collection.
2. Import and rebuild (needs Python 3 and `pip install Pillow`):
   ```
   python3 tools/photos.py import ~/Exports/big-bend --collection big-bend --title "Big Bend"
   python3 tools/photos.py build
   ```
   Re-running `import` on the same folder skips photos already added.
3. Optional: edit `photos/collections.json` to reorder photos, change a collection's `cover`, or fill in `alt`, `caption` and `buy_url` (adds a "Buy print" link in the viewer). Run `build` again after editing.
4. Commit and push (on a branch, then merge to `master` to publish).

To remove a photo: delete its entry from `collections.json`, delete its two files under `photos/`, run `build`.

## License

All rights not expressly stated in a license in this repository are hereby exclusive to Matthew Fawks. All images and code, unless otherwise stated, are also for the exclusive use and distribution of Matthew Fawks.
