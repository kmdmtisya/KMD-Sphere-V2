import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../app/app_routes.dart';
import '../../../core/auth/auth_controller.dart';
import '../../../core/auth/oidc_client.dart';
import '../../../l10n/generated/app_localizations.dart';
import '../../../shared/design_system/components/components.dart';
import '../../../shared/design_system/theme/wealth_typography.dart';
import '../../../shared/design_system/tokens/tokens.dart';
import '../application/auth_flow.dart';
import 'biometric_offer.dart';

/// Screen 2: Sign In / Sign Up.
///
/// Credentials, MFA codes and password resets are entered only on the identity provider's
/// hosted pages (Authorization Code + PKCE). The app collects at most an email to pre-fill
/// that page, and shows plain error messages that reveal nothing about accounts or tokens.
class SignInScreen extends ConsumerStatefulWidget {
  const SignInScreen({super.key});

  @override
  ConsumerState<SignInScreen> createState() => _SignInScreenState();
}

class _SignInScreenState extends ConsumerState<SignInScreen> {
  final _form = GlobalKey<FormState>();
  final _email = TextEditingController();
  bool _resetFailed = false;

  @override
  void dispose() {
    _email.dispose();
    super.dispose();
  }

  String? get _hint {
    final value = _email.text.trim();
    return value.isEmpty ? null : value;
  }

  void _start({required bool register}) {
    setState(() => _resetFailed = false);
    if (!(_form.currentState?.validate() ?? false)) return;
    unawaited(
      ref
          .read(authControllerProvider.notifier)
          .signIn(loginHint: _hint, register: register),
    );
  }

  Future<void> _reset() async {
    final opened = await ref.read(passwordResetLauncherProvider).open();
    if (mounted) setState(() => _resetFailed = !opened);
  }

  Future<void> _onSignedIn() async {
    await offerBiometricsOnce(context, ref);
    if (mounted) context.go(AppRoutes.home);
  }

  @override
  Widget build(BuildContext context) {
    ref.listen(authControllerProvider, (previous, next) {
      if (next is SignedIn && previous is! SignedIn) unawaited(_onSignedIn());
    });
    final l10n = AppLocalizations.of(context);
    final auth = ref.watch(authControllerProvider);
    final busy = auth is SigningIn || auth is AuthRestoring;
    final banner = switch (auth) {
      SignedOut(ended: _?) => l10n.accountSessionExpired,
      SignedOut(failure: AuthFailure.network) => l10n.accountSignInOffline,
      SignedOut(failure: _?) => l10n.accountSignInFailed,
      _ => _resetFailed ? l10n.signInResetFailed : null,
    };
    return Scaffold(
      appBar: AppBar(title: Text(l10n.signInTitle)),
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(AppSpacing.m),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 480),
              child: Form(
                key: _form,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Text(l10n.signInIntro, style: context.wealthText.body),
                    const SizedBox(height: AppSpacing.m),
                    if (banner != null) ...[
                      StatusBanner(
                        key: const ValueKey('sign-in-error'),
                        icon: Icons.error_outline,
                        message: banner,
                      ),
                      const SizedBox(height: AppSpacing.m),
                    ],
                    TextFormField(
                      key: const ValueKey('sign-in-email'),
                      controller: _email,
                      enabled: !busy,
                      keyboardType: TextInputType.emailAddress,
                      autofillHints: const [AutofillHints.email],
                      autocorrect: false,
                      textInputAction: TextInputAction.done,
                      maxLength: maxEmailLength,
                      buildCounter: (
                        _, {
                        required currentLength,
                        required isFocused,
                        maxLength,
                      }) => null,
                      decoration: InputDecoration(
                        labelText: l10n.signInEmailLabel,
                        hintText: l10n.signInEmailHint,
                      ),
                      autovalidateMode: AutovalidateMode.onUserInteraction,
                      validator: (value) =>
                          switch (validateLoginHint(value ?? '')) {
                            EmailProblem.invalid => l10n.signInEmailInvalid,
                            EmailProblem.tooLong => l10n.signInEmailTooLong,
                            null => null,
                          },
                      onFieldSubmitted: (_) => _start(register: false),
                    ),
                    const SizedBox(height: AppSpacing.m),
                    if (busy) ...[
                      const LinearProgressIndicator(),
                      const SizedBox(height: AppSpacing.m),
                    ],
                    FilledButton.icon(
                      key: const ValueKey('continue-sign-in'),
                      onPressed: busy ? null : () => _start(register: false),
                      icon: const Icon(Icons.login),
                      label: Text(l10n.signInContinue),
                    ),
                    const SizedBox(height: AppSpacing.s),
                    OutlinedButton.icon(
                      key: const ValueKey('create-account'),
                      onPressed: busy ? null : () => _start(register: true),
                      icon: const Icon(Icons.person_add_alt),
                      label: Text(l10n.signInCreateAccount),
                    ),
                    const SizedBox(height: AppSpacing.xs),
                    TextButton(
                      key: const ValueKey('forgot-password'),
                      onPressed: busy ? null : _reset,
                      child: Text(l10n.signInForgotPassword),
                    ),
                    const SizedBox(height: AppSpacing.m),
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        ExcludeSemantics(
                          child: Icon(
                            Icons.verified_user_outlined,
                            size: 20,
                            color: context.wealthColors.textMuted,
                          ),
                        ),
                        const SizedBox(width: AppSpacing.s),
                        Expanded(
                          child: Text(
                            l10n.signInMfaNote,
                            style: context.wealthText.caption,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: AppSpacing.l),
                    TextButton(
                      key: const ValueKey('explore-demo'),
                      onPressed: busy ? null : () => context.go(AppRoutes.home),
                      child: Text(l10n.signInExploreDemo),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
