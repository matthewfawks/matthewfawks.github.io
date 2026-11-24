# matthewfawks.com

Personal site of Matthew Fawks. Plain HTML/CSS, served by GitHub Pages from the `master` branch (no Jekyll; see `.nojekyll`).

## Layout

| Path | What it is |
|---|---|
| `index.html` | Resume home page |
| `documents/matthew-fawks-resume.pdf` | Resume PDF linked from the home page (replace the file to update it) |
| `photography/index.html` | Photography landing page (hero, collections, prints, about) |
| `photography/<collection>/index.html` | Gallery pages. **Generated**; don't edit by hand |
| `photos/<collection>/full/`, `thumb/` | Web-sized photos (2400 px / 800 px, metadata stripped) |
| `photos/collections.json` | Order, titles, covers, alt text, captions and print links for every photo |
| `tools/photos.py` | Photo import + gallery build script |
| `assets/` | CSS, JS (gallery lightbox), images (headshot, flying, about photo), favicon |
| `collection-*.html` | Redirects from the old site's gallery URLs |

## Managing photos

All photo work goes through `tools/photos.py`. Every command rebuilds the gallery pages when it finishes, so the site is ready to commit straight after.

**One-time setup on a Mac:** install [GitHub Desktop](https://desktop.github.com) and clone this repo, then in Terminal run `pip3 install Pillow` (say yes if macOS offers to install developer tools). Run the commands below from the repo folder (`cd` into it first).

### Add or replace photos

1. Export from Lightroom: JPEG, sRGB, long edge 2400 px, quality 90+, metadata "All Metadata" with location info **included** (the script reads location and camera details for the captions, then strips everything, GPS included, from the published files). One folder per collection: `landscapes`, `cityscapes`, `architecture-streets`, `art-details`, `wildlife`, `panoramas`.
2. Import:
   ```
   python3 tools/photos.py import ~/Desktop/exports/landscapes --collection landscapes
   ```
   Photos already on the site are skipped. To fix a photo (location, edit, crop), re-export it with the **same file name** into the same folder and import again: it is replaced in place. A new collection needs `--title "Its Title"` the first time.

### Keep the site in step with your folders (easiest)

```
python3 tools/photos.py sync ~/Desktop/"Website Redesign (Claude Files)"/~image-collections
```
Treats each folder (`landscapes`, `cityscapes`, ...) as that collection: photos you deleted or moved out come off the site, new and re-exported photos go on, and a photo moved to another folder moves to that collection. Folders starting with `_` or `~` (for example `_removed`) are ignored.

### See what's on the site

```
python3 tools/photos.py list              # every collection
python3 tools/photos.py list landscapes   # one collection
```
Shows each photo's site name (`landscapes-021`), its Lightroom number (`158`, from `FPTS-20261123-158.jpg`) and its location. Commands below accept either.

### Change a cover

```
python3 tools/photos.py cover landscapes 158
```

Photos show in each gallery in Lightroom file-name order (FPTS-…-001, 002, …), left to right.

### Remove photos

```
python3 tools/photos.py remove 158 cityscapes-012
```
Deletes the photo's entry and both image files. Also delete it from your export folder, or the next `import` of that folder adds it back.

### Publish

Open GitHub Desktop, check the changed files, commit and push. Pushing to `master` updates the live site in about a minute; pushing to another branch only updates its pull request.

### Hand edits (optional)

`photos/collections.json` holds everything else: collection titles and descriptions, `alt` text, `caption`, a `buy_url` per photo (adds a "Buy print" link in the viewer) and `"layout": "wide"` (one photo per row, used for panoramas). After editing it, run `python3 tools/photos.py build`.

## License

All rights not expressly stated in a license in this repository are hereby exclusive to Matthew Fawks. All images and code, unless otherwise stated, are also for the exclusive use and distribution of Matthew Fawks.
