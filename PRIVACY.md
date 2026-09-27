# AURA Privacy Policy

Applies to the AURA web app and the AURA Android app (`com.oscarhickman.aura`). Last updated 27 September 2026.

## Who runs the service

AURA is self-hosted research software. The Android app has no central AURA service: it connects only to the AURA server address you enter in its settings, which you or your organisation run. The developer of the app receives no data from the app.

## What the app stores on your device

- The server address you configure.
- An API access token issued by your server when you sign in. It is removed when you sign out.
- Cached paper lists for offline reading.

## What is sent to your AURA server

- Your email address and password when you sign in (used only to issue the access token).
- Your paper ratings, reading-list changes, and questions you ask about papers.

Your server stores this data to rank papers for you. Questions you ask about a paper may be sent, together with that paper's text, to the language-model provider your server's administrator has configured (for example Groq, OpenAI or Anthropic).

## What we do not do

- No advertising, analytics or tracking SDKs.
- No sale or sharing of personal data with third parties.
- No access to your contacts, location, camera, microphone or files. The app requests internet access only.

## Deleting your data

Signing out removes the token and cached data from your device, and uninstalling the app removes everything it stored. To delete your account and the data held on the server, contact the administrator of your AURA server.

## Contact

Questions about this policy: <https://github.com/OscarHickman/aura/issues>
