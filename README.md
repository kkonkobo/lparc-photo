# LPARC Photo

ID photos from a webcam, saved as `<matricule>.jpg`. Version 2 is a rebuild of *Application Photo LPARC V1.2*
(whose source was recovered from the V1.2 executable) for Windows and macOS.

## Using it

1. Type the matricule and press **Entrée** (or click *Prendre la photo*).
2. Check the photo, then **Entrée** to save or **Échap** to retake.

The frame follows the face automatically. Turn off *Cadrage automatique* to frame by hand: drag the image to move
the frame, scroll to zoom. Settings are remembered between sessions.

Output size defaults to the V1.2 format (413 × 532 px, 35 × 45 mm at 300 dpi). Pick another preset or
*Personnalisé…* to set any size in millimetres or pixels at any resolution, as JPEG or lossless PNG.

On macOS, an iPhone near the Mac shows up as a camera (Continuity Camera) and gives much better photos than the
built-in webcam.

## What changed since V1.2

| V1.2 | V2 |
| --- | --- |
| Camera's default resolution (often 640 × 480) | Best mode the camera offers, up to 2560 × 1440 |
| Fixed crop from the top-left corner of the frame | Crop centred on the face, or framed by hand |
| Crop saved as-is, possibly shorter than 532 px | Always the exact output size, resampled with Lanczos, DPI written to the file |
| JPEG at OpenCV's default quality 95 with 4:2:0 chroma | Adjustable quality, full 4:4:4 chroma, or PNG |
| Saved to whatever the current folder is | Chosen folder, *~/Pictures/LPARC Photos* by default |
| Existing photo: error | Shows the existing photo and offers to replace it |
| Camera 0/1 toggle | Camera list with names, hot-plug aware |
| Windows only, 63 MB single exe | Windows and macOS (Apple Silicon and Intel) |

## Development

Requires [uv](https://docs.astral.sh/uv/).

```sh
uv run lparc-photo                                    # run from source
uv run pytest                                         # tests (no camera needed)
uv run pyinstaller packaging/lparc_photo.spec --noconfirm   # build into dist/
uv run python packaging/make_assets.py                # redraw icon and UI glyphs
```

PyInstaller cannot cross-compile: each OS builds its own app. GitHub Actions (`.github/workflows/build.yml`)
builds Windows, macOS Apple Silicon and macOS Intel on every push; the zips are under the run's *Artifacts*.
Pushing a tag such as `v2.0.0` publishes them as a GitHub Release.

### Unsigned builds

The builds are not signed with a paid certificate, so the first launch shows a warning:

- **macOS**: right-click the app, choose *Ouvrir*, then *Ouvrir* again. macOS asks for camera access on first use.
- **Windows**: SmartScreen shows *Windows a protégé votre ordinateur*: click *Informations complémentaires*, then
  *Exécuter quand même*.

Signing needs an Apple Developer account (macOS) and a code-signing certificate (Windows).

## Download site

`site/` is the download page at https://lparc-photo.yibe.studio: a static page in an nginx container on Dokploy.
`/download/windows`, `/download/mac` and `/download/mac-intel` redirect to the newest GitHub Release, so shared links
never change. `.github/workflows/deploy-site.yml` rebuilds and redeploys it whenever `site/` changes on `main`.

Releasing a new version of the app: bump `__version__` in `src/lparc_photo/__init__.py` and `version` in
`pyproject.toml`, then push a tag such as `v2.1.0`. The site picks the new release up by itself.
