import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/core/auth/token_set.dart';
import 'package:wealthsphere_app/core/auth/token_store.dart';
import 'package:wealthsphere_app/core/config/app_config.dart';

import '../../helpers/auth_fakes.dart';

void main() {
  group('TokenSet', () {
    test('reads a token response relative to now', () {
      final t = TokenSet.fromTokenResponse({
        'access_token': 'a',
        'refresh_token': 'r',
        'expires_in': 300,
        'id_token': 'i',
      }, now: epoch);
      expect(t.accessTokenExpiresAt, epoch.add(const Duration(minutes: 5)));
      expect(t.refreshToken, 'r');
      expect(t.idToken, 'i');
    });

    test(
      'keeps the previous refresh token only when the response has none',
      () {
        final rotated = TokenSet.fromTokenResponse(
          {'access_token': 'a', 'refresh_token': 'new', 'expires_in': 60},
          now: epoch,
          previousRefreshToken: 'old',
        );
        expect(rotated.refreshToken, 'new');
        final kept = TokenSet.fromTokenResponse(
          {'access_token': 'a', 'expires_in': 60},
          now: epoch,
          previousRefreshToken: 'old',
        );
        expect(kept.refreshToken, 'old');
        expect(
          () => TokenSet.fromTokenResponse({
            'access_token': 'a',
            'expires_in': 60,
          }, now: epoch),
          throwsFormatException,
        );
      },
    );

    test('rejects malformed responses', () {
      expect(
        () => TokenSet.fromTokenResponse({
          'refresh_token': 'r',
          'expires_in': 60,
        }, now: epoch),
        throwsFormatException,
      );
      expect(
        () => TokenSet.fromTokenResponse({
          'access_token': 'a',
          'refresh_token': 'r',
          'expires_in': '60',
        }, now: epoch),
        throwsFormatException,
      );
    });

    test('knows when the access token is about to expire', () {
      final t = tokens('a', expiresAt: epoch.add(const Duration(seconds: 60)));
      expect(t.expiresWithin(const Duration(seconds: 30), epoch), isFalse);
      expect(t.expiresWithin(const Duration(seconds: 60), epoch), isTrue);
      expect(
        t.expiresWithin(Duration.zero, epoch.add(const Duration(minutes: 2))),
        isTrue,
      );
    });

    test('round-trips through JSON', () {
      final t = tokens('a');
      final back = TokenSet.fromJson(
        jsonDecode(jsonEncode(t.toJson())) as Map<String, Object?>,
      );
      expect(back.accessToken, t.accessToken);
      expect(back.refreshToken, t.refreshToken);
      expect(back.accessTokenExpiresAt, t.accessTokenExpiresAt);
      expect(back.idToken, t.idToken);
    });

    test('never prints a token', () {
      final t = tokens('secret-user');
      final text = '$t ${[t]}';
      expect(text, isNot(contains(t.accessToken)));
      expect(text, isNot(contains(t.refreshToken)));
      expect(text, isNot(contains(t.idToken)));
      expect(text, contains('[REDACTED]'));
    });

    test('exposes display claims and survives garbage', () {
      expect(tokens('a').displayClaims['email'], 'alice@example.test');
      final garbage = TokenSet(
        accessToken: 'not-a-jwt',
        refreshToken: 'r',
        accessTokenExpiresAt: epoch,
      );
      expect(garbage.displayClaims, isEmpty);
    });
  });

  group('SecureTokenStore', () {
    late Map<String, String> platform;

    setUp(() {
      platform = {};
      FlutterSecureStorage.setMockInitialValues(platform);
    });

    test('writes, reads and clears one entry in secure storage', () async {
      final store = SecureTokenStore();
      expect(await store.read(), isNull);
      await store.write(tokens('a'));
      expect(platform.keys, [SecureTokenStore.key]);
      expect((await store.read())!.refreshToken, 'refresh-a');
      await store.clear();
      expect(platform, isEmpty);
      expect(await store.read(), isNull);
    });

    test('an unreadable entry is discarded, not trusted', () async {
      platform[SecureTokenStore.key] = '{"access_token": 42';
      expect(await SecureTokenStore().read(), isNull);
      expect(platform, isEmpty);
    });

    test('iOS items stay on this device and are not synced', () {
      final options = SecureTokenStore.defaultStorage.iOptions.toMap();
      expect(options['accessibility'], 'first_unlock_this_device');
      expect(options['synchronizable'], 'false');
    });
  });

  group('AppConfig', () {
    const local = AppConfig(
      apiBaseUrl: 'http://127.0.0.1:8000',
      oidcIssuer: 'http://127.0.0.1:8081/realms/wealthsphere/',
    );

    test('derives the Keycloak endpoints from the issuer', () {
      expect(
        local.tokenEndpoint,
        'http://127.0.0.1:8081/realms/wealthsphere/protocol/openid-connect/token',
      );
      expect(
        local.authorizationEndpoint,
        endsWith('/protocol/openid-connect/auth'),
      );
      expect(
        local.endSessionEndpoint,
        endsWith('/protocol/openid-connect/logout'),
      );
    });

    test('never asks for offline tokens', () {
      expect(local.scopes, isNot(contains('offline_access')));
      expect(local.scopes, contains('openid'));
    });

    test('plain HTTP is allowed only to loopback hosts in debug builds', () {
      expect(local.allowsInsecureConnections, isTrue);
      local.assertSecureFor(debug: true);
      expect(() => local.assertSecureFor(debug: false), throwsStateError);
      const remote = AppConfig(
        apiBaseUrl: 'http://api.example.com',
        oidcIssuer: 'https://id.example.com/realms/wealthsphere',
      );
      expect(() => remote.assertSecureFor(debug: true), throwsStateError);
      const secure = AppConfig(
        apiBaseUrl: 'https://api.example.com',
        oidcIssuer: 'https://id.example.com/realms/wealthsphere',
      );
      secure.assertSecureFor(debug: false);
      expect(secure.allowsInsecureConnections, isFalse);
    });

    test('the default configuration is valid for this build', () {
      expect(AppConfig.fromEnvironment, returnsNormally);
      expect(
        kDebugMode,
        isTrue,
      ); // tests run as debug: local HTTP defaults are accepted
    });
  });
}
