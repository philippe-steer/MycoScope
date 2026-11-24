# Publishing MycoScope on F-Droid — checklist

The repository is already public and contains no signing key, so only two steps remain.

## 1. Tag the release
After merging this branch, tag `main` as `v0.2.2` (GitHub → Releases → *Draft a new release* → tag `v0.2.2`).
F-Droid builds from that tag and reads the store texts from `fastlane/metadata/android/`.

Each later release needs a new `versionCode`/`versionName` in `app/build.gradle.kts`, a changelog
`fastlane/metadata/android/<lang>/changelogs/<versionCode>.txt`, and a `vX.Y.Z` tag
(F-Droid picks it up automatically: `AutoUpdateMode: Version`). Data tags (`data-v1`, `sources-*`, `latest`) are ignored.

## 2. Submit to F-Droid (once)
1. Create an account on https://gitlab.com.
2. Fork https://gitlab.com/fdroid/fdroiddata.
3. Copy `fdroid/fr.mycoscope.yml` to `metadata/fr.mycoscope.yml` in your fork.
4. Open a merge request titled "New app: MycoScope". F-Droid's CI builds the app; reviewers may ask questions
   (e.g. category names, or the habitat file read online from GitHub releases — it is open data
   produced by this repository's own `pipeline/`).
5. Once merged, the app appears in F-Droid within a few days.

Screenshots can be added in `fastlane/metadata/android/fr-FR/images/phoneScreenshots/` (PNG/JPG).
