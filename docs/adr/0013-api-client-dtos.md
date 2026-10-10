# ADR-0013: Mobile API client DTOs (hand-written, contract-checked)

Status: Proposed (P05-T10, 2026-10-10; for user approval at P05-GATE)

## Context
P03-T01 built the mobile DTOs for DEMO data, before the API existed. P05 built the API, and P05-T10 must decide how the app keeps its DTOs in step with `backend/openapi.json`. The plan assumed Freezed DTOs; in practice every DTO is a hand-written class parsed by the strict `JsonReader` (`lib/core/data/json_reader.dart`), and `freezed`, `json_serializable` and `build_runner` are declared in `pubspec.yaml` but not used.

Options considered:
1. **Generate a Dart client from OpenAPI** (openapi-generator, swagger_parser). Follows the spec automatically, but the generated models parse money and decimals with the generator's defaults (JSON numbers, `double`), which breaks ADR-0003 unless every type is overridden. It also adds a code-generation step to every API change.
2. **Freezed + json_serializable.** Less boilerplate, but the converters for `Money`, decimals and timestamps would have to re-implement what `JsonReader` already enforces (string amounts, no JSON numbers, field path in every error). It also adds generated files to review.
3. **Hand-written DTOs on `JsonReader`, checked against the spec in CI.** Keeps the strict parsing that already exists and is tested. The drift risk is handled by a contract check.

## Decision
1. **Option 3.** DTOs stay hand-written and parse only through `JsonReader`. No generated client and no Freezed for API DTOs.
2. **The contract is `docs/contracts/dto-mapping.json`.** For each DTO with a live API it lists every field (same, renamed, dto-only or api-only), and for each difference a resolution and the task that owns it. DTOs whose API is not built yet are listed with their JSON keys and owning task. `docs/contracts/dto-mapping.md` is generated from it (`scripts/dto_mapping.py`).
3. **CI enforces it** (`backend/tests/test_dto_mapping.py`, in the backend gate, which also runs when the Dart sources, the mapping or the plan change):
   - every API path and field it names exists in `backend/openapi.json`, nested fields included;
   - the keys each live DTO class reads equal the keys mapped for it, so a field added to or removed from a DTO fails the build until the mapping is updated;
   - every difference has a resolution and an owner that is a real task;
   - the Markdown matches the JSON.
4. **Field names follow the API.** Where they differ today, the live repositories (P09-T02 to P09-T04) map API fields onto the DTOs; a DTO field with no API source (for example `profit_loss`) is filled only from a server endpoint, never derived in the app.

## Consequences
- Money and decimal parsing stays in one strict, tested place (ADR-0003).
- Some boilerplate per DTO; acceptable at the current number of endpoints. Revisit if the API grows past what the mapping can track comfortably.
- The check verifies names and presence, not types. Types are covered by `JsonReader` failing loudly at run time and by the live-repository tests in P09.
- The unused `freezed`, `json_serializable` and `build_runner` dependencies can be removed in P09-T01 (API client framework), unless another use is found.
