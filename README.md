# LPARC Photo

ID photos from a webcam, saved as `<matricule>.jpg`. Version 2 is a rebuild of *Application Photo LPARC V1.2*
(whose source was recovered from the V1.2 executable) for Windows and macOS.

## Using it

1. Type the matricule and press **Entrée** (or click *Prendre la photo*).
2. Check the photo, then **Entrée** to save or **Échap** to retake.

The frame follows the face automatically and places it as on an ID photo; scroll to tighten or widen it. Turn off
*Cadrage automatique* to frame by hand: drag the image to move the frame, scroll to zoom. Settings are remembered
between sessions.

Under *Arrière-plan*, or on the review screen, choose *Blanc*, *Bleu clair* or *Autre…* to replace the real
background with a plain colour. *Conserver aussi l'original* keeps the untouched photo in an `originaux` subfolder.
The cut-out is best with even light and a seat without a high back (a chair back behind the shoulders stays in the
picture).

Output size defaults to the V1.2 format (413 × 532 px, 35 × 45 mm at 300 dpi). Pick another preset or
*Personnalisé…* to set any size in millimetres or pixels at any resolution, as JPEG or lossless PNG.

On macOS, an iPhone near the Mac shows up as a camera (Continuity Camera) and gives much better photos than the
built-in webcam.

## What changed since V1.2

| V1.2 | V2 |
| --- | --- |
| Camera's default resolution (often 640 × 480) | Best mode the camera offers, up to 2560 × 1440 |
| Fixed crop from the top-left corner of the frame | Framed on the face like an ID photo, or by hand |
| Real background only | White, light blue or any plain colour, original kept on request |
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
uv run lparc-photo --self-test tests/data/portrait.jpg report.json   # face + background check, no window
```

Face detection (YuNet) and background removal (MODNet, run with ONNX Runtime) use the models in
`src/lparc_photo/models/`; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). The build pipeline runs the
`--self-test` above on each packaged app, so a build that cannot find a face or replace a background fails.

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
`pyproject.toml`, then push a tag such as `v2.3.0`. The site picks the new release up by itself.

## Installing and updating

- **Windows**: `LPARC-Photo-windows-x64-setup.exe` installs for the current user (no administrator rights needed),
  with Start-menu and desktop shortcuts. Running a newer installer upgrades the existing install in place; settings
  and photos are kept. The `.zip` is a portable copy that needs no installation. The installer is built with
  [Inno Setup](https://jrsoftware.org/isinfo.php) from `packaging/installer.iss`; the build pipeline installs it,
  runs the installed app's self-test, upgrades it and uninstalls it.
- **macOS**: drag the new app into *Applications* and replace the old one.
- **Update notice**: at start-up the app asks `https://lparc-photo.yibe.studio/latest` which version is newest and
  shows a *Télécharger* banner when it is newer than the running one. It sends nothing but that request, stays
  silent when offline, and can be turned off under *Mises à jour*.
