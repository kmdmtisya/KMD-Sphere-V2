import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../l10n/generated/app_localizations.dart';
import '../../shared/design_system/components/components.dart';
import '../connectivity/connectivity.dart';
import '../data/demo_support.dart';
import '../network/api_client.dart';

/// Whether the offline banner is up: live data and the API unreachable.
bool connectivityBannerVisible(WidgetRef ref) =>
    ref.watch(dataSourceModeProvider) == DataSourceMode.live &&
    !ref.watch(onlineProvider);

/// Shown above every tab while the API cannot be reached: "You're offline", with the age of the
/// saved data on screen, and a Retry that checks the connection (and, if it is back, reloads
/// every live screen). Nothing is shown in DEMO mode or while online.
class ConnectivityBanner extends ConsumerStatefulWidget {
  const ConnectivityBanner({this.now, super.key});

  /// Injectable clock for tests.
  final DateTime? now;

  @override
  ConsumerState<ConnectivityBanner> createState() => _ConnectivityBannerState();
}

class _ConnectivityBannerState extends ConsumerState<ConnectivityBanner> {
  bool _checking = false;

  Future<void> _retry() async {
    if (_checking) return;
    setState(() => _checking = true);
    try {
      // Any answer from the server marks the app online (the API client's offline interceptor).
      await ref
          .read(apiClientProvider)
          .get<Object?>(
            '/health/live',
            options: Options(extra: {ApiOptions.public: true}),
          );
    } on Object {
      // Still offline: the banner stays.
    } finally {
      if (mounted) setState(() => _checking = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!connectivityBannerVisible(ref)) return const SizedBox.shrink();
    final l10n = AppLocalizations.of(context);
    final savedAt = ref.watch(savedDataAsOfProvider);
    return StatusBanner(
      icon: Icons.wifi_off_rounded,
      message: savedAt == null
          ? l10n.offlineBannerNoSavedData
          : l10n.offlineBannerWithAge(
              dataAsOfText(
                l10n,
                savedAt,
                now: widget.now ?? DateTime.now(),
                locale: context.formatLocale,
              ),
            ),
      actionLabel: _checking ? null : l10n.retry,
      onAction: _checking ? null : () => unawaited(_retry()),
    );
  }
}
