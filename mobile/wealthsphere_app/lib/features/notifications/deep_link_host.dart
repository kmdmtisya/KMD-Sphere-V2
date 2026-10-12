import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'notification_service.dart';

/// Opens a tapped notification's screen once the user is signed in, then forgets it. Also keeps
/// the device registered for notifications while signed in.
class DeepLinkHost extends ConsumerWidget {
  const DeepLinkHost({required this.router, required this.child, super.key});

  final GoRouter router;
  final Widget child;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    ref.watch(notificationWiringProvider);
    final open = ref.watch(deepLinkToOpenProvider);
    if (open != null) {
      // After this frame, so the route change never lands in the middle of a build.
      WidgetsBinding.instance.addPostFrameCallback((_) {
        router.go(open.path);
        ref.read(pendingDeepLinkProvider.notifier).clear();
      });
    }
    return child;
  }
}
