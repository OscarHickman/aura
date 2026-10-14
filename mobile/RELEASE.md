# Android release checklist

## Verified locally (2026-10-14)

- TypeScript, Jest unit/component tests, and the mobile-to-Flask contract test.
- Android production JavaScript export with Hermes.
- Android native project generation with `expo prebuild --platform android --no-install`.
- Generated manifest permits the configured HTTP home server and disables Android app backup.

- Signed release App Bundle (`.aab`) targeting Android API 36 built with Hermes and the `aura-upload` key.
- Registered application on Google Play Console under package `com.oscarhickman.aura` (App ID `4974729963301483997`).
- Uploaded and published initial release 1 (1.0.0) to the Internal testing track.
- Configured tester email access (`Oscar`) with test join link: `https://play.google.com/apps/internaltest/4700935800772390515`.


## Repeatable checks

From `mobile/`:

```sh
pnpm install --frozen-lockfile
pnpm typecheck
pnpm test:ci
AURA_CONTRACT_PYTHON=../.venv/bin/python pnpm exec jest --runInBand contract.test.js
pnpm exec expo export --platform android --output-dir /tmp/aura-android-export
pnpm exec expo prebuild --platform android --no-install
```

The contract test starts a Flask test client in a child Python process and uses a temporary SQLite database. It needs backend dependencies but no running server, live API keys, or network port. CI runs it in the Python 3.11 job; the mobile-only job skips it.

With an Android SDK and a compatible JDK configured, build the generated project:

```sh
cd android
./gradlew bundleRelease assembleRelease --no-daemon
```

Without release signing configuration, these artifacts use the generated development key. Use the workflow's signing configuration before distribution.

## Upload key custody

Generate the upload key on a trusted machine, outside the checkout, with passwords entered at prompts:

```sh
keytool -genkeypair -v -keystore /secure/path/aura-upload.jks \
  -alias aura-upload -keyalg RSA -keysize 3072 -validity 10000
keytool -list -v -keystore /secure/path/aura-upload.jks -alias aura-upload
```

Record the alias and certificate fingerprints. Keep two encrypted backups in separate locations and store the keystore/key passwords in a password manager. Verify a restored copy with `keytool -list` before relying on it. Do not commit keystores, passwords, or service-account JSON. Base64 encoding is not encryption.

Populate the secrets consumed by `.github/workflows/deploy.yml`:

- `ANDROID_KEYSTORE_BASE64`: base64 of the upload keystore.
- `KEYSTORE_PASSWORD`, `KEY_ALIAS`, `KEY_PASSWORD`.
- `GOOGLE_PLAY_SERVICE_ACCOUNT_JSON`: the publishing service account's JSON credentials.

If an upload key is lost or compromised, use the app's Play Console signing settings to request the supported reset/recovery process. Preserve the existing signing arrangement; do not silently generate a replacement key for an established listing.

## Release sequence

1. Run CI and review the changes. Complete the app listing, privacy URL, screenshots and console requirements.
2. In **Build and Deploy**, run `workflow_dispatch` with `build_android=true`. This builds Android artifacts without uploading to Play; the workflow also builds/pushes the backend container image.
3. Download the workflow's APK/AAB artifacts. Check signing fingerprints and install the APK on a test phone.
4. Verify login, server-path prefixes, pagination/search, reading-list caching, notes, background/foreground transitions, offline startup and reconnect. Sign in as a second account and check that the first account's cached papers and pending actions are absent.
5. Complete the initial Play Console setup/upload as required for the app. Use the `internal` track first. Check `GOOGLE_PLAY_RELEASE_STATUS` against the app's current console state; the workflow defaults to `completed`.
6. Only after those checks, create the intended `vX.Y.Z` tag. Tagging triggers server deployment, release artifacts and conditional Play publishing. Confirm all jobs and download/install the released build.

The workflow derives release `versionCode` as `major * 10000 + minor * 100 + patch`. Keep minor/patch below 100 and increase the version for each new Play build; rerunning the same tag reuses its code. Do not promote to production until internal testing is complete.

## Data behavior for release review

The standalone app sends credentials and authenticated API requests to the server address the user selects. The server can call research sources and configured LLM providers. Opening paper/PDF links opens external sites. No analytics, crash reporting or push SDK is integrated in this version.

The app stores a bearer token, server address, cached user/paper/note data, and pending changes in app-private AsyncStorage. This is not an encrypted credential vault. Cached data and queues are scoped by server and user ID. Signing out removes active credentials; scoped caches and unsent changes remain available for that same account's next login. Uninstalling/clearing app data removes them. Android backup is disabled. HTTP is enabled for LAN/Tailscale servers; use HTTPS for connections that need transport encryption outside a trusted network or VPN.

Old unscoped queues are not automatically replayed because their owner/server cannot be established safely. Their storage is left untouched. Note replay deduplication requires the updated backend; deploy it before the updated app.
