import 'package:dio/dio.dart';
import 'package:flutter_appauth/flutter_appauth.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:wealthsphere_app/core/auth/oidc_client.dart';
import 'package:wealthsphere_app/core/config/app_config.dart';

import '../../helpers/auth_fakes.dart';

class MockAppAuth extends Mock implements FlutterAppAuth {}

const config = AppConfig(
  apiBaseUrl: 'http://127.0.0.1:8000',
  oidcIssuer: 'http://127.0.0.1:8081/realms/wealthsphere',
);

Matcher failsWith(AuthFailure failure) =>
    throwsA(isA<AuthException>().having((e) => e.failure, 'failure', failure));

void main() {
  setUpAll(() {
    registerFallbackValue(
      AuthorizationTokenRequest('c', 'r', issuer: 'https://fallback.example'),
    );
  });

  group('refresh', () {
    late FakeAdapter adapter;
    late KeycloakOidcClient client;

    setUp(() {
      adapter = FakeAdapter();
      client = KeycloakOidcClient(
        config: config,
        appAuth: MockAppAuth(),
        http: Dio()..httpClientAdapter = adapter,
        clock: () => epoch,
      );
    });

    test('posts the refresh grant for the public client and rotates', () async {
      adapter.replies.add(
        reply(200, {
          'access_token': 'new-access',
          'refresh_token': 'new-refresh',
          'expires_in': 300,
        }),
      );
      final fresh = await client.refresh(tokens('a'));
      final sent = adapter.sent.single;
      expect(sent.options.uri.toString(), config.tokenEndpoint);
      expect(sent.options.method, 'POST');
      expect(
        sent.header('content-type'),
        contains('application/x-www-form-urlencoded'),
      );
      expect(Uri.splitQueryString(sent.body), {
        'grant_type': 'refresh_token',
        'client_id': 'wealthsphere-mobile',
        'refresh_token': 'refresh-a',
      });
      expect(fresh.accessToken, 'new-access');
      expect(fresh.refreshToken, 'new-refresh');
      expect(
        fresh.accessTokenExpiresAt,
        epoch.add(const Duration(seconds: 300)),
      );
    });

    test('a refused grant is "rejected"', () async {
      adapter.replies.add(reply(400, {'error': 'invalid_grant'}));
      await expectLater(
        client.refresh(tokens('a')),
        failsWith(AuthFailure.rejected),
      );
      adapter.replies.add(reply(401, {'error': 'invalid_client'}));
      await expectLater(
        client.refresh(tokens('a')),
        failsWith(AuthFailure.rejected),
      );
    });

    test(
      'server trouble and transport errors are transient "network" failures',
      () async {
        adapter.replies
          ..add(reply(503))
          ..add(reply(429))
          ..add(DioExceptionType.connectionError)
          ..add(DioExceptionType.receiveTimeout);
        for (var i = 0; i < 4; i++) {
          await expectLater(
            client.refresh(tokens('a')),
            failsWith(AuthFailure.network),
          );
        }
      },
    );

    test('a malformed success response is "unexpected"', () async {
      adapter.replies.add(reply(200, {'token': 'x'}));
      await expectLater(
        client.refresh(tokens('a')),
        failsWith(AuthFailure.unexpected),
      );
    });

    test('end session posts the refresh token and never throws', () async {
      adapter.replies
        ..add(reply(204))
        ..add(DioExceptionType.connectionError);
      await client.endSession(tokens('a'));
      expect(
        adapter.sent.single.options.uri.toString(),
        config.endSessionEndpoint,
      );
      expect(Uri.splitQueryString(adapter.sent.single.body), {
        'client_id': 'wealthsphere-mobile',
        'refresh_token': 'refresh-a',
      });
      await client.endSession(tokens('a')); // offline: swallowed
    });
  });

  group('sign-in (Authorization Code + PKCE via AppAuth)', () {
    late MockAppAuth appAuth;
    late KeycloakOidcClient client;

    setUp(() {
      appAuth = MockAppAuth();
      client = KeycloakOidcClient(
        config: config,
        appAuth: appAuth,
        http: Dio(),
      );
    });

    AuthorizationTokenResponse response({
      String? access = 'access',
      String? refresh = 'refresh',
      DateTime? expiry,
    }) => AuthorizationTokenResponse(
      access,
      refresh,
      expiry ?? epoch,
      'id',
      'Bearer',
      ['openid'],
      null,
      null,
    );

    test(
      'requests the code flow for the mobile client with the realm endpoints',
      () async {
        when(() => appAuth.authorizeAndExchangeCode(any()))
            .thenAnswer((_) async => response());
        final t = await client.signIn();
        expect(t.accessToken, 'access');
        expect(t.refreshToken, 'refresh');
        final request =
            verify(() => appAuth.authorizeAndExchangeCode(captureAny()))
                    .captured
                    .single
                as AuthorizationTokenRequest;
        expect(request.clientId, 'wealthsphere-mobile');
        expect(
          request.redirectUrl,
          'com.kmdmtisya.wealthsphere:/oauth2redirect',
        );
        expect(request.grantType, 'authorization_code');
        expect(
          request.serviceConfiguration!.authorizationEndpoint,
          config.authorizationEndpoint,
        );
        expect(
          request.serviceConfiguration!.tokenEndpoint,
          config.tokenEndpoint,
        );
        expect(request.scopes, isNot(contains('offline_access')));
        expect(
          request.externalUserAgent,
          ExternalUserAgent.ephemeralAsWebAuthenticationSession,
        );
        expect(
          request.clientSecret,
          isNull,
        ); // public client: no secret on the device
      },
    );

    test(
      'login hint, registration and MFA set-up use the hosted pages',
      () async {
        when(() => appAuth.authorizeAndExchangeCode(any()))
            .thenAnswer((_) async => response());
        await client.signIn(loginHint: 'alice@example.test');
        await client.signIn(intent: SignInIntent.register);
        await client.signIn(intent: SignInIntent.configureMfa);
        final requests = verify(
          () => appAuth.authorizeAndExchangeCode(captureAny()),
        ).captured.cast<AuthorizationTokenRequest>();
        expect(requests[0].loginHint, 'alice@example.test');
        expect(requests[0].promptValues, isNull);
        expect(requests[0].additionalParameters, isNull);
        expect(requests[1].promptValues, ['create']);
        expect(requests[2].additionalParameters, {
          'kc_action': 'CONFIGURE_TOTP',
        });
      },
    );

    test('closing the browser is "cancelled"', () async {
      when(() => appAuth.authorizeAndExchangeCode(any())).thenThrow(
        FlutterAppAuthUserCancelledException(
          code: 'authorize_and_exchange_code_failed',
          platformErrorDetails: FlutterAppAuthPlatformErrorDetails(),
        ),
      );
      await expectLater(client.signIn(), failsWith(AuthFailure.cancelled));
    });

    test('provider errors map to rejected, network or unexpected', () async {
      FlutterAppAuthPlatformException failure(String? error) =>
          FlutterAppAuthPlatformException(
            code: 'authorize_and_exchange_code_failed',
            platformErrorDetails: FlutterAppAuthPlatformErrorDetails(
              error: error,
            ),
          );
      when(() => appAuth.authorizeAndExchangeCode(any()))
          .thenThrow(failure('invalid_grant'));
      await expectLater(client.signIn(), failsWith(AuthFailure.rejected));
      when(() => appAuth.authorizeAndExchangeCode(any()))
          .thenThrow(failure(null));
      await expectLater(client.signIn(), failsWith(AuthFailure.network));
      when(() => appAuth.authorizeAndExchangeCode(any()))
          .thenThrow(failure('invalid_scope'));
      await expectLater(client.signIn(), failsWith(AuthFailure.unexpected));
    });

    test('an incomplete token response is refused', () async {
      when(() => appAuth.authorizeAndExchangeCode(any()))
          .thenAnswer((_) async => response(refresh: null));
      await expectLater(client.signIn(), failsWith(AuthFailure.unexpected));
    });
  });
}
