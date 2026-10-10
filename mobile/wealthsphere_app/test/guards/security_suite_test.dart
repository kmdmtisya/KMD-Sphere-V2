import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// Every test file for a mobile security control carries the `security` tag, so
/// `flutter test --tags security` (its own CI step) runs all of them. Keep in step with
/// docs/threat-model.md.
const securityTestFiles = {
  'test/core/auth/token_set_test.dart':
      'token set, secure token store, app config (https only)',
  'test/core/auth/token_manager_test.dart':
      'refresh, rotation, single-flight, session end',
  'test/core/auth/keycloak_oidc_client_test.dart':
      'PKCE sign-in request, error mapping',
  'test/core/network/api_client_test.dart':
      'bearer handling, 401 retry, no token leaks',
  'test/core/security/app_lock_test.dart': 'device authentication, lock policy',
  'test/core/security/app_lock_gate_test.dart':
      'lock screen, privacy cover, idle lock',
  'test/features/account/account_section_test.dart': 'sign-in/out, MFA set-up',
  'test/features/auth/auth_screens_test.dart':
      'auth screens, non-leaking errors',
};

void main() {
  for (final entry in securityTestFiles.entries) {
    test('${entry.key} is tagged security (${entry.value})', () {
      final source = File(entry.key).readAsStringSync();
      expect(source, startsWith("@Tags(['security'])"));
    });
  }
}
