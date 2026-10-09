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
