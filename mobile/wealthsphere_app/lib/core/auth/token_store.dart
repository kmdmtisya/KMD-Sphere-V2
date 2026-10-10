import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import 'token_set.dart';

/// Where session tokens live between app launches. Only secure storage in production: never
/// shared preferences, files or logs.
abstract interface class TokenStore {
  Future<TokenSet?> read();
  Future<void> write(TokenSet tokens);
  Future<void> clear();
}

/// [TokenStore] in the Android Keystore-backed encrypted storage / iOS Keychain.
///
/// iOS items are `first_unlock_this_device`: readable for background refresh after the first
/// unlock, never synced to iCloud or restored onto another device. Android auto-backup is off
/// for the app (AndroidManifest), so encrypted values are not restored where their key is gone.
class SecureTokenStore implements TokenStore {
  SecureTokenStore([this._storage = defaultStorage]);

  static const defaultStorage = FlutterSecureStorage(
    iOptions: IOSOptions(
      accessibility: KeychainAccessibility.first_unlock_this_device,
      synchronizable: false,
    ),
    aOptions: AndroidOptions(),
  );

  static const key = 'ws.auth.tokens.v1';
  final FlutterSecureStorage _storage;

  @override
  Future<TokenSet?> read() async {
    final raw = await _storage.read(key: key);
    if (raw == null) return null;
    try {
      return TokenSet.fromJson(jsonDecode(raw) as Map<String, Object?>);
    } on Object {
      // Unreadable or from an older format: start signed out rather than fail.
      await clear();
      return null;
    }
  }

  @override
  Future<void> write(TokenSet tokens) =>
      _storage.write(key: key, value: jsonEncode(tokens.toJson()));

  @override
  Future<void> clear() => _storage.delete(key: key);
}

/// Volatile store for tests, previews and demo mode.
class InMemoryTokenStore implements TokenStore {
  InMemoryTokenStore([this.tokens]);

  TokenSet? tokens;

  @override
  Future<TokenSet?> read() async => tokens;

  @override
  Future<void> write(TokenSet tokens) async => this.tokens = tokens;

  @override
  Future<void> clear() async => tokens = null;
}

/// The active store. `main()` overrides it with [SecureTokenStore]; the in-memory default keeps
/// tests and previews from touching platform storage (and never persists anything).
final tokenStoreProvider = Provider<TokenStore>((ref) => InMemoryTokenStore());
