import 'dart:async';

import 'package:wealthsphere_app/core/security/device_authenticator.dart';

/// Scriptable [DeviceAuthenticator]: queue outcomes; records every prompt.
class FakeDeviceAuthenticator implements DeviceAuthenticator {
  FakeDeviceAuthenticator({this.available = true});

  bool available;
  final List<UnlockOutcome> outcomes = [];
  final List<String> prompts = [];

  /// When set, prompts wait for it (to test what happens while the prompt is open).
  Completer<void>? gate;

  @override
  Future<bool> isAvailable() async => available;

  @override
  Future<UnlockOutcome> authenticate(String reason) async {
    prompts.add(reason);
    await gate?.future;
    if (outcomes.isEmpty) return UnlockOutcome.cancelled;
    return outcomes.removeAt(0);
  }
}
