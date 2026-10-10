import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/auth/auth_controller.dart';
import '../../../core/auth/oidc_client.dart';
import '../../../l10n/generated/app_localizations.dart';
import '../../../shared/design_system/components/components.dart';
import '../../../shared/design_system/theme/wealth_typography.dart';
import '../../../shared/design_system/tokens/tokens.dart';
import '../data/account_repository.dart';
import 'app_lock_settings_tile.dart';

/// Sign in / sign out and the server's view of the account. Temporary home in the More tab
/// until the auth screens (P04-T08) and Settings exist.
class AccountSection extends ConsumerWidget {
  const AccountSection({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    final auth = ref.watch(authControllerProvider);
    final controller = ref.read(authControllerProvider.notifier);
    return WealthCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(l10n.accountTitle, style: context.wealthText.title),
          const SizedBox(height: AppSpacing.s),
          ...switch (auth) {
            AuthRestoring() => [const LinearProgressIndicator()],
            SigningIn() => [
              Text(l10n.accountSigningIn),
              const SizedBox(height: AppSpacing.s),
              const LinearProgressIndicator(),
            ],
            SignedOut(:final ended, :final failure) => [
              if (ended != null) ...[
                StatusBanner(
                  icon: Icons.lock_clock,
                  message: l10n.accountSessionExpired,
                ),
                const SizedBox(height: AppSpacing.s),
              ] else if (failure != null) ...[
                StatusBanner(
                  icon: Icons.error_outline,
                  message: failure == AuthFailure.network
                      ? l10n.accountSignInOffline
                      : l10n.accountSignInFailed,
                ),
                const SizedBox(height: AppSpacing.s),
              ],
              Text(l10n.accountSignedOutHint, style: context.wealthText.body),
              const SizedBox(height: AppSpacing.s),
              FilledButton.icon(
                key: const ValueKey('sign-in'),
                onPressed: controller.signIn,
                icon: const Icon(Icons.login),
                label: Text(l10n.accountSignIn),
              ),
            ],
            SignedIn(:final email) => [
              Text(
                email == null
                    ? l10n.accountSignedIn
                    : l10n.accountSignedInAs(email),
                style: context.wealthText.body,
              ),
              const SizedBox(height: AppSpacing.xs),
              const _ServerAccount(),
              const SizedBox(height: AppSpacing.s),
              const AppLockSettingsTile(),
              const SizedBox(height: AppSpacing.s),
              OutlinedButton.icon(
                key: const ValueKey('sign-out'),
                onPressed: controller.signOut,
                icon: const Icon(Icons.logout),
                label: Text(l10n.accountSignOut),
              ),
            ],
          },
        ],
      ),
    );
  }
}

class _ServerAccount extends ConsumerWidget {
  const _ServerAccount();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    final style = context.wealthText.caption;
    final account = ref.watch(currentAccountProvider);
    // Riverpod retries failed providers, so an error can arrive as "loading with an error".
    if (account.value case final value?) {
      return Text(
        l10n.accountServerCheck(value.email ?? value.id),
        style: style,
      );
    }
    if (account.hasError) return Text(l10n.accountServerError, style: style);
    return const SizedBox.shrink();
  }
}
