import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/connectivity/connectivity.dart';
import '../application/forex_providers.dart';

/// Keeps the quote stream in step with the app (QG-19.3, QG-19.5): paused when the app goes to
/// the background or the device goes offline, resumed at once when it comes back. Wraps the
/// screens that show live prices.
class ForexStreamScope extends ConsumerStatefulWidget {
  const ForexStreamScope({required this.child, super.key});

  final Widget child;

  @override
  ConsumerState<ForexStreamScope> createState() => _ForexStreamScopeState();
}

class _ForexStreamScopeState extends ConsumerState<ForexStreamScope> {
  late final AppLifecycleListener _lifecycle;
  bool _hidden = false;

  @override
  void initState() {
    super.initState();
    _lifecycle = AppLifecycleListener(
      onHide: () {
        _hidden = true;
        unawaited(ref.read(forexStreamProvider).pause());
      },
      onShow: () {
        _hidden = false;
        if (ref.read(onlineProvider)) {
          unawaited(ref.read(forexStreamProvider).resume());
        }
      },
    );
  }

  @override
  void dispose() {
    _lifecycle.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    ref.listen<bool>(onlineProvider, (_, online) {
      final stream = ref.read(forexStreamProvider);
      if (!online) {
        unawaited(stream.pause());
      } else if (!_hidden) {
        unawaited(stream.resume());
      }
    });
    // Keeps the merged quotes (and so the stream) alive while the scope is shown.
    ref.watch(liveQuotesProvider);
    return widget.child;
  }
}
