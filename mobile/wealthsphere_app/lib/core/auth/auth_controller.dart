import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'oidc_client.dart';
import 'token_manager.dart';

/// What the UI knows about the session. Never carries tokens.
@immutable
sealed class AuthState {
  const AuthState();
}

/// Reading the stored session at start-up.
class AuthRestoring extends AuthState {
  const AuthRestoring();
}

class SignedOut extends AuthState {
  const SignedOut({this.ended, this.failure});

  /// Set when the session ended on its own (expired or refused), so the UI can say so.
  final SessionEnd? ended;

  /// Set when the last sign-in attempt failed (null when it was cancelled).
  final AuthFailure? failure;

  @override
  bool operator ==(Object other) =>
      other is SignedOut && other.ended == ended && other.failure == failure;

  @override
  int get hashCode => Object.hash(ended, failure);
}

class SigningIn extends AuthState {
  const SigningIn();
}

class SignedIn extends AuthState {
  const SignedIn({this.email});

  /// From the access token, for display only.
  final String? email;

  @override
  bool operator ==(Object other) => other is SignedIn && other.email == email;

  @override
  int get hashCode => email.hashCode;
}

class AuthController extends Notifier<AuthState> {
  late TokenManager _tokens;

  @override
  AuthState build() {
    _tokens = ref.watch(tokenManagerProvider);
    _tokens.onSessionEnded = (reason) {
      if (ref.mounted) state = SignedOut(ended: reason);
    };
    unawaited(_restore());
    return const AuthRestoring();
  }

  Future<void> _restore() async {
    final signedIn = await _tokens.restore();
    if (!ref.mounted || state is! AuthRestoring) return;
    state = signedIn ? _signedIn() : const SignedOut();
  }

  /// Signs in (or, with [register], creates an account) on the identity provider's pages.
  Future<void> signIn({String? loginHint, bool register = false}) async {
    if (state is SigningIn) return;
    state = const SigningIn();
    try {
      await _tokens.signIn(
        loginHint: loginHint,
        intent: register ? SignInIntent.register : SignInIntent.signIn,
      );
      if (ref.mounted) state = _signedIn();
    } on AuthException catch (e) {
      if (!ref.mounted) return;
      state = SignedOut(
        failure: e.failure == AuthFailure.cancelled ? null : e.failure,
      );
    }
  }

  /// Runs the identity provider's two-step verification set-up for the signed-in user. Returns
  /// null on success (or cancellation); the current session is kept whatever happens.
  Future<AuthFailure?> setUpTwoStepVerification() async {
    if (state is! SignedIn) return AuthFailure.signedOut;
    try {
      await _tokens.signIn(intent: SignInIntent.configureMfa);
      if (ref.mounted) state = _signedIn();
      return null;
    } on AuthException catch (e) {
      return e.failure == AuthFailure.cancelled ? null : e.failure;
    }
  }

  Future<void> signOut() async {
    await _tokens.signOut();
    if (ref.mounted) state = const SignedOut();
  }

  SignedIn _signedIn() {
    final email = _tokens.claims['email'];
    return SignedIn(email: email is String ? email : null);
  }
}

final authControllerProvider = NotifierProvider<AuthController, AuthState>(
  AuthController.new,
);
