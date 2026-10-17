# AURA Android Mobile App

Modern Android companion app for AURA (Automated Understanding of Research Articles), built with **React Native**, **Expo**, and **TypeScript**.

---

## Key Features

1. **Triage Deck**: Fast, one-handed triage deck to quickly like, skip, or bookmark recommended papers and train your preference model.
2. **Paper Feed**: Scrollable ranked feed with pull-to-refresh, real-time match scores, and instant search across titles, authors, and arXiv categories.
3. **Paper Detail & AI Q&A**: Clean reading view with AI summaries, links to arXiv/PDF, and an interactive Q&A assistant to ask questions about the paper directly to the home server's LLM backend.
4. **Reading List**: Saved papers separated into Unread and Read history, with offline paper/note caching and queued changes that sync when the app reconnects.
5. **Server Connection Manager**: Configurable server address with connection testing and persistent Bearer token authentication.

---

## Connecting to Your Home Server

The app connects to your AURA backend over HTTP/HTTPS:

* **Home Network (Wi-Fi):** `http://<home-server-lan-ip>:5000`
* **Tailscale (Remote / On the go):** `http://100.88.127.35/aura` (pre-configured default)

Open the **Settings** tab in the app to test the connection and log in with your account credentials.

---

## Local Development & Testing on Your Phone

You do not need to install the heavy Android SDK on your desktop machine to develop or test on your phone.

1. Install **Expo Go** from the Google Play Store on your Android phone.
2. Make sure your phone is connected to your local Wi-Fi network (or Tailscale).
3. Start the development server from the repository root:
   ```bash
   cd mobile
   pnpm install
   pnpm start
   ```
4. Scan the QR code displayed in your terminal with the Expo Go app. The app will immediately load on your phone with live reload enabled.

---

---

## Automated Deployment & Google Play Release

This repository is synced to GitHub and configured for continuous deployment on new git tags:

1. When you create and push a git tag (e.g. `git tag v1.0.0 && git push origin v1.0.0`):
   * **Home Server:** GitHub Actions builds the Docker image and auto-deploys the backend to your home server over Tailscale (`100.88.127.35`).
   * **GitHub Releases:** Generates and uploads standalone `aura-<tag>.apk` and `aura-<tag>.aab` binaries.
   * **Google Play Store:** If secrets are configured, signs the `.aab` bundle and publishes it directly to your Google Play track (`internal`, `alpha`, or `production`).

### Google Play Secrets Configuration (GitHub Repository Settings)

To enable automatic publishing to Google Play, add these secrets under **Settings > Secrets and variables > Actions**:

| Secret Name | Description |
|---|---|
| `GOOGLE_PLAY_SERVICE_ACCOUNT_JSON` | Service account JSON key with "Releases" permission in Google Play Console. |
| `ANDROID_KEYSTORE_BASE64` | Base64-encoded upload keystore (`base64 -w 0 upload.keystore`). |
| `KEYSTORE_PASSWORD` | Password for your keystore. |
| `KEY_ALIAS` | Alias name for the key in your keystore. |
| `KEY_PASSWORD` | Password for your key alias. |

*(Optional)* Under **Variables > Actions**, set `GOOGLE_PLAY_TRACK` to `internal` (default), `alpha`, `beta`, or `production`.


## Quality checks and release status

```sh
pnpm typecheck
pnpm test:ci
AURA_CONTRACT_PYTHON=../.venv/bin/python pnpm exec jest --runInBand contract.test.js
```

Jest covers API/auth behavior and the main screens. The contract test uses the real Flask routes and a temporary database; install the backend dependencies before running it. CI enforces 80% statement/function/line coverage for API/auth code and compiles the Android JavaScript bundle.

See [RELEASE.md](RELEASE.md) for verified build steps, remaining physical-device/signing checks, key backup, and the release sequence. Native project generation and JavaScript export have passed locally; a signed APK/AAB and Play upload remain unverified.

Offline changes are stored separately for each server/account. Opening Settings shows pending changes and offers manual sync; foreground sync retries every 30 seconds while signed in. Changing the server signs out locally. Cached content and pending changes remain scoped to their original account. Install the updated backend before using note replay deduplication.
