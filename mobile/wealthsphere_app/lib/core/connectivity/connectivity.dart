import 'package:flutter_riverpod/flutter_riverpod.dart';

/// Whether the device is online.
///
/// Until the network layer arrives (P09-T06, with the platform connectivity signal) this is a
/// plain state the app and tests can set, so offline behaviour can be built and tested now.
class ConnectivityNotifier extends Notifier<bool> {
  @override
  bool build() => true;

  void setOnline({required bool online}) => state = online;
}

final onlineProvider = NotifierProvider<ConnectivityNotifier, bool>(
  ConnectivityNotifier.new,
);
