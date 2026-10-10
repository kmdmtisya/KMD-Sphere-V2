import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../l10n/generated/app_localizations.dart';
import '../../shared/design_system/theme/wealth_typography.dart';
import '../../shared/design_system/tokens/tokens.dart';
import '../auth/auth_controller.dart';
import 'app_lock_controller.dart';
import 'app_lock_settings.dart';
import 'device_authenticator.dart';

/// Wraps the whole app (from `MaterialApp.builder`):
///
/// - While locked, the app is offstage (not painted, not hit-testable, hidden from screen
///   readers) and its animations are paused; the lock screen is shown instead.
/// - While the app is inactive (app switcher, system dialogs) a privacy cover hides its content,
///   so the switcher snapshot shows no financial data.
/// - Reports background/resume and touch inactivity to [AppLockController].
class AppLockGate extends ConsumerStatefulWidget {
  const AppLockGate({required this.child, super.key});

  final Widget child;

  @override
  ConsumerState<AppLockGate> createState() => _AppLockGateState();
}

class _AppLockGateState extends ConsumerState<AppLockGate> {
  late final AppLifecycleListener _lifecycle;
  Timer? _idle;
  bool _covered = false;

  AppLockController get _lock => ref.read(appLockControllerProvider.notifier);

  @override
  void initState() {
    super.initState();
    _lifecycle = AppLifecycleListener(
      onInactive: () => setState(() => _covered = true),
      onHide: () {
        _idle?.cancel();
        _lock.onBackgrounded();
      },
      onResume: () {
        setState(() => _covered = false);
        _lock.onResumed();
        _restartIdle();
        _promptIfJustLocked(ref.read(appLockControllerProvider));
      },
    );
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _restartIdle();
      _promptIfJustLocked(ref.read(appLockControllerProvider));
    });
  }

  @override
  void dispose() {
    _idle?.cancel();
    _lifecycle.dispose();
    super.dispose();
  }

  void _restartIdle() {
    _idle?.cancel();
    _idle = Timer(AppLockSettings.idleTimeout, () {
      if (mounted) _lock.onIdle();
    });
  }

  /// Opens the system prompt once when the lock engages; after a failed attempt the user retries.
  void _promptIfJustLocked(AppLockState state) {
    final resumed = WidgetsBinding.instance.lifecycleState;
    if (state is Locked &&
        state.lastOutcome == null &&
        (resumed == null || resumed == AppLifecycleState.resumed)) {
      unawaited(_lock.unlock(AppLocalizations.of(context).lockReason));
    }
  }

  @override
  Widget build(BuildContext context) {
    ref.listen(appLockControllerProvider, (previous, next) {
      if (previous is Unlocked) _promptIfJustLocked(next);
      if (next is Unlocked) _restartIdle();
    });
    final lock = ref.watch(appLockControllerProvider);
    final locked = lock is! Unlocked;
    return Listener(
      behavior: HitTestBehavior.translucent,
      onPointerDown: (_) => _restartIdle(),
      child: Stack(
        children: [
          // Offstage: not painted, not hit-testable and absent from the semantics tree.
          Offstage(
            offstage: locked,
            child: TickerMode(enabled: !locked, child: widget.child),
          ),
          if (locked) LockScreen(state: lock),
          if (_covered) const PrivacyCover(),
        ],
      ),
    );
  }
}

class LockScreen extends ConsumerWidget {
  const LockScreen({required this.state, super.key});

  final AppLockState state;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    final colors = context.wealthColors;
    final outcome = state is Locked ? (state as Locked).lastOutcome : null;
    final message = switch (outcome) {
      UnlockOutcome.failed => l10n.lockFailed,
      UnlockOutcome.lockedOut => l10n.lockLockedOut,
      UnlockOutcome.unavailable => l10n.lockUnavailable,
      _ => null,
    };
    final canTry = state is Locked && outcome != UnlockOutcome.unavailable;
    return Scaffold(
      key: const ValueKey('lock-screen'),
      backgroundColor: colors.scaffold,
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(AppSpacing.l),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Icon(Icons.lock_outline, size: 48, color: colors.primary),
                  const SizedBox(height: AppSpacing.m),
                  Semantics(
                    header: true,
                    child: Text(
                      l10n.lockTitle,
                      style: context.wealthText.headline,
                      textAlign: TextAlign.center,
                    ),
                  ),
                  const SizedBox(height: AppSpacing.s),
                  Text(
                    l10n.lockBody,
                    style: context.wealthText.body,
                    textAlign: TextAlign.center,
                  ),
                  if (message != null) ...[
                    const SizedBox(height: AppSpacing.m),
                    Semantics(
                      liveRegion: true,
                      child: Text(
                        message,
                        key: const ValueKey('lock-message'),
                        style: context.wealthText.body.copyWith(
                          color: colors.negativeText,
                        ),
                        textAlign: TextAlign.center,
                      ),
                    ),
                  ],
                  const SizedBox(height: AppSpacing.l),
                  FilledButton.icon(
                    key: const ValueKey('unlock'),
                    onPressed: canTry
                        ? () => ref
                              .read(appLockControllerProvider.notifier)
                              .unlock(l10n.lockReason)
                        : null,
                    icon: const Icon(Icons.fingerprint),
                    label: Text(l10n.lockUnlock),
                  ),
                  const SizedBox(height: AppSpacing.s),
                  TextButton(
                    key: const ValueKey('lock-sign-out'),
                    onPressed: () =>
                        ref.read(authControllerProvider.notifier).signOut(),
                    child: Text(l10n.lockSignOut),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Opaque cover shown while the app is inactive (for the app switcher snapshot).
class PrivacyCover extends StatelessWidget {
  const PrivacyCover({super.key});

  @override
  Widget build(BuildContext context) {
    final colors = context.wealthColors;
    return Positioned.fill(
      key: const ValueKey('privacy-cover'),
      child: Semantics(
        label: AppLocalizations.of(context).privacyCoverLabel,
        child: ColoredBox(
          color: colors.scaffold,
          child: Center(
            child: Icon(Icons.shield_outlined, size: 64, color: colors.primary),
          ),
        ),
      ),
    );
  }
}
