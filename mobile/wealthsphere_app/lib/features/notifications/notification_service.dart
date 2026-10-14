import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/app_routes.dart';
import '../../core/auth/auth_controller.dart';
import '../../core/data/demo_support.dart';
import '../../core/network/api_client.dart';
import '../../core/network/live_repository.dart';

/// Where a notification may send the user: only screens inside the app, from a fixed list.
/// Anything else (an unknown route, a URL, another scheme) is ignored (ADR-0016).
@immutable
class NotificationRoute {
  const NotificationRoute._(this.path);

  final String path;

  static const _allowed = {
    AppRoutes.home,
    AppRoutes.portfolio,
    AppRoutes.goals,
    AppRoutes.alerts,
    AppRoutes.transactions,
    // Forex (P13-T11): the forex home, the calendar and paper trading.
    AppRoutes.forex,
    AppRoutes.forexCalendar,
    AppRoutes.forexPaper,
  };

  /// The route in a notification payload, or null when it is missing or not allowed. The payload
  /// carries a type, ids and a route only; it never carries amounts.
  static NotificationRoute? fromPayload(Map<String, Object?> payload) {
    final route = payload['route'];
    if (route is! String) return null;
    final uri = Uri.tryParse(route);
    if (uri == null || uri.hasScheme || uri.hasAuthority) return null;
    return _allowed.contains(uri.path) ? NotificationRoute._(uri.path) : null;
  }
}

/// A notification the user tapped, waiting for a signed-in session before it opens its screen.
class PendingDeepLinkNotifier extends Notifier<NotificationRoute?> {
  @override
  NotificationRoute? build() => null;

  /// Called by the platform push handler when the user opens a notification (or a link). An
  /// unusable payload is dropped.
  void received(Map<String, Object?> payload) {
    final route = NotificationRoute.fromPayload(payload);
    if (route != null) state = route;
  }

  void clear() => state = null;
}

final pendingDeepLinkProvider =
    NotifierProvider<PendingDeepLinkNotifier, NotificationRoute?>(
      PendingDeepLinkNotifier.new,
    );

/// The route to open now: the pending one, once the user is signed in. Null otherwise (the link
/// waits through sign-in and is dropped at sign-out).
final deepLinkToOpenProvider = Provider<NotificationRoute?>((ref) {
  final pending = ref.watch(pendingDeepLinkProvider);
  final auth = ref.watch(authControllerProvider);
  return pending != null && auth is SignedIn ? pending : null;
});

// ------------------------------------------------------------------------------- devices

/// Where the device's push token comes from (FCM, once the Firebase project exists, ADR-0016).
abstract interface class PushTokenSource {
  /// The token, or null when push is not available on this device or build.
  Future<({String platform, String token})?> token();
}

class NoPushTokenSource implements PushTokenSource {
  const NoPushTokenSource();

  @override
  Future<({String platform, String token})?> token() async => null;
}

final pushTokenSourceProvider = Provider<PushTokenSource>(
  (ref) => const NoPushTokenSource(),
);

abstract interface class DeviceRepository {
  /// Registers this device; returns its id.
  Future<String> register({required String platform, required String token});
  Future<void> remove(String deviceId);
}

class LiveDeviceRepository extends LiveRepository implements DeviceRepository {
  const LiveDeviceRepository(super.dio);

  @override
  Future<String> register({required String platform, required String token}) =>
      send(
        'POST',
        '/api/v1/devices',
        (r) => r.string('id'),
        body: {'platform': platform, 'token': token},
      );

  @override
  Future<void> remove(String deviceId) =>
      sendEmpty('DELETE', '/api/v1/devices/$deviceId');
}

/// In DEMO mode nothing is registered anywhere.
class NoDeviceRepository implements DeviceRepository {
  const NoDeviceRepository();

  @override
  Future<String> register({
    required String platform,
    required String token,
  }) async => 'demo-device';

  @override
  Future<void> remove(String deviceId) async {}
}

final deviceRepositoryProvider = Provider<DeviceRepository>(
  (ref) => ref.watch(dataSourceModeProvider) == DataSourceMode.live
      ? LiveDeviceRepository(ref.watch(apiClientProvider))
      : const NoDeviceRepository(),
);

/// Registers this device for notifications while a user is signed in, and removes it at
/// sign-out. A failure never blocks the app: notifications are best effort, and the in-app list
/// shows every alert either way.
class DeviceRegistrar {
  DeviceRegistrar(this._ref);

  final Ref _ref;
  String? _deviceId;

  Future<void> onSignedIn() async {
    try {
      final source = await _ref.read(pushTokenSourceProvider).token();
      if (source == null) return;
      _deviceId = await _ref
          .read(deviceRepositoryProvider)
          .register(platform: source.platform, token: source.token);
    } on Object {
      // Best effort.
    }
  }

  /// Call before the session ends where possible. After it ends the server cannot be asked, and
  /// the device simply stops being used.
  Future<void> onSignOut() async {
    final id = _deviceId;
    _deviceId = null;
    if (id == null) return;
    try {
      await _ref.read(deviceRepositoryProvider).remove(id);
    } on Object {
      // Best effort.
    }
  }
}

final deviceRegistrarProvider = Provider<DeviceRegistrar>(DeviceRegistrar.new);

/// Wires sign-in and sign-out to device registration. Watched once by the app.
final notificationWiringProvider = Provider<void>((ref) {
  ref.listen<AuthState>(authControllerProvider, (previous, next) {
    final registrar = ref.read(deviceRegistrarProvider);
    if (next is SignedIn && previous is! SignedIn) {
      unawaited(registrar.onSignedIn());
    } else if (previous is SignedIn && next is! SignedIn) {
      unawaited(registrar.onSignOut());
      // A link that was waiting for this user is not for the next one.
      ref.read(pendingDeepLinkProvider.notifier).clear();
    }
  }, fireImmediately: true);
});
