# Local server credentials

Place the Firebase service-account key at:

```text
secrets/firebase-service-account.json
```

This directory is for local, server-side secrets only. Never put a service
account JSON file in source control, a frontend bundle, a screenshot, or a
support message. The placeholder `.gitkeep` is the only credential-directory
file intended to be committed.

See [`docs/FIREBASE_SETUP.md`](../docs/FIREBASE_SETUP.md) for the complete
setup, verification, rotation, and troubleshooting steps.
