# Developer environment

Verified on Windows 11 on 2026-10-09 (task P01-T01).

| Tool | Version | Notes |
|---|---|---|
| Flutter / Dart | 3.47.5 / 3.13.4 | `flutter doctor`: all sections OK |
| Android SDK | platform 36, build-tools 28.0.3 and 36.0.0 | licences accepted; installed with `sdkmanager` |
| Android emulators | `Pixel_8_Pro`, `Medium_Phone_API_36` | `flutter emulators --launch Pixel_8_Pro` |
| Python / uv | 3.14.5 / 0.12.20 | backend needs Python 3.13+ |
| Docker | 29.5.3 | Docker Desktop must be running (`docker info`) |
| Terraform | 1.16.5 | installed with winget; open a new shell to pick up PATH |
| Git / gh / Node / make | 2.56.0 / 2.101 / 24.16 / 4.4.1 | |

iOS cannot be built on Windows. CI compiles it on macOS (P01-T10); device QA needs a Mac or cloud device.

## Quick checks

```bash
flutter doctor          # all [√]
docker info             # server answers
terraform version
python --version && uv --version
flutter emulators --launch Pixel_8_Pro
```

## Local stack (P01-T05)

```bash
cp .env.example .env     # then replace every CHANGE_ME (dev values only; .env is git-ignored)
make up                  # docker compose up -d --wait
make ps | make logs | make down | make reset   # reset DESTROYS local data volumes
```

| Service | Host port (default) | Notes |
|---|---|---|
| PostgreSQL 17 + pgvector | 5433 | databases `wealthsphere` and `keycloak`; extensions `vector`, `pgcrypto` |
| Redis 7 | 6380 | password required |
| RabbitMQ 4 | 5673 (AMQP), 15673 (management UI) | |
| Keycloak 26.4 (start-dev) | 8081 (health on 9001) | realm and client are configured in P04-T01 |

Host ports differ from the usual defaults so the stack can run beside other local services. Override them in `.env`. All ports bind to 127.0.0.1 only.

## Mobile app

```bash
cd mobile/wealthsphere_app
flutter pub get && flutter gen-l10n
dart format --output=none --set-exit-if-changed . && flutter analyze && flutter test
flutter build apk --debug && flutter install -d emulator-5554
```
The first Android build also needs NDK 28.2.13676358 (`sdkmanager --install "ndk;28.2.13676358"`).
