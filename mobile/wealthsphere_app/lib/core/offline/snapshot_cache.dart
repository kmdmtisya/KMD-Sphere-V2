import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart' as hash;
import 'package:cryptography/cryptography.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:path_provider/path_provider.dart';

import '../auth/token_manager.dart';

/// The last good answer to one request, and when it was saved.
@immutable
class Snapshot {
  const Snapshot(this.body, this.savedAt);

  /// The decoded JSON body, exactly as the server sent it.
  final Object? body;
  final DateTime savedAt;
}

/// The last good API answers, kept so the app can show them when it is offline (ADR-0015).
abstract interface class SnapshotCache {
  /// The saved answer to [request] for the signed-in user, or null.
  Future<Snapshot?> read(String request);

  Future<void> write(String request, Object? body, DateTime savedAt);

  /// Deletes every saved answer of every user, and the key. Called at sign-out and when the
  /// session ends.
  Future<void> wipe();
}

/// Where the cache key lives: the platform secure storage in the app, memory in tests.
abstract interface class CacheKeyStore {
  Future<List<int>?> read();
  Future<void> write(List<int> key);
  Future<void> delete();
}

class SecureCacheKeyStore implements CacheKeyStore {
  const SecureCacheKeyStore([this._storage = const FlutterSecureStorage()]);

  static const _name = 'ws.offline_cache.key';
  final FlutterSecureStorage _storage;

  @override
  Future<List<int>?> read() async {
    final text = await _storage.read(key: _name);
    return text == null ? null : base64Decode(text);
  }

  @override
  Future<void> write(List<int> key) =>
      _storage.write(key: _name, value: base64Encode(key));

  @override
  Future<void> delete() => _storage.delete(key: _name);
}

class InMemoryCacheKeyStore implements CacheKeyStore {
  List<int>? key;

  @override
  Future<List<int>?> read() async => key;

  @override
  Future<void> write(List<int> key) async => this.key = key;

  @override
  Future<void> delete() async => key = null;
}

/// Snapshots as files, each encrypted with AES-256-GCM under one device key kept in secure
/// storage. Files sit in a folder per user (a hash of the user's subject) and are named by a hash
/// of the request, so neither ids nor amounts are readable on disk. With no signed-in user
/// nothing is read or written.
class EncryptedSnapshotCache implements SnapshotCache {
  EncryptedSnapshotCache({
    required this._root,
    required this._keys,
    required this._user,
  });

  final Future<Directory> Function() _root;
  final CacheKeyStore _keys;
  final String? Function() _user;
  final AesGcm _aes = AesGcm.with256bits();
  SecretKey? _key;

  static String _hash(String text) =>
      hash.sha256.convert(utf8.encode(text)).toString();

  Future<File?> _file(String request) async {
    final user = _user();
    if (user == null || user.isEmpty) return null;
    final root = await _root();
    final dir = Directory('${root.path}/ws_offline/${_hash('user:$user')}');
    return File('${dir.path}/${_hash(request)}.bin');
  }

  Future<SecretKey> _secret() async {
    final known = _key;
    if (known != null) return known;
    final stored = await _keys.read();
    if (stored != null && stored.length == 32) {
      return _key = SecretKey(stored);
    }
    final fresh = await _aes.newSecretKey();
    await _keys.write(await fresh.extractBytes());
    return _key = fresh;
  }

  @override
  Future<Snapshot?> read(String request) async {
    final file = await _file(request);
    if (file == null || !file.existsSync()) return null;
    try {
      final box = SecretBox.fromConcatenation(
        await file.readAsBytes(),
        nonceLength: _aes.nonceLength,
        macLength: _aes.macAlgorithm.macLength,
      );
      final clear = await _aes.decrypt(box, secretKey: await _secret());
      final json = jsonDecode(utf8.decode(clear)) as Map<String, Object?>;
      return Snapshot(
        json['body'],
        DateTime.parse(json['saved_at']! as String),
      );
    } on Object {
      return null; // a different key (reinstall, wipe) or a damaged file: treat as absent
    }
  }

  @override
  Future<void> write(String request, Object? body, DateTime savedAt) async {
    final file = await _file(request);
    if (file == null) return;
    final clear = utf8.encode(
      jsonEncode({'saved_at': savedAt.toUtc().toIso8601String(), 'body': body}),
    );
    final box = await _aes.encrypt(clear, secretKey: await _secret());
    await file.parent.create(recursive: true);
    await file.writeAsBytes(box.concatenation(), flush: true);
  }

  @override
  Future<void> wipe() async {
    _key = null;
    await _keys.delete();
    final dir = Directory('${(await _root()).path}/ws_offline');
    if (dir.existsSync()) await dir.delete(recursive: true);
  }
}

/// A plain in-memory cache for widget tests.
class MemorySnapshotCache implements SnapshotCache {
  final Map<String, Snapshot> entries = {};
  int wipes = 0;

  @override
  Future<Snapshot?> read(String request) async => entries[request];

  @override
  Future<void> write(String request, Object? body, DateTime savedAt) async =>
      entries[request] = Snapshot(body, savedAt);

  @override
  Future<void> wipe() async {
    wipes++;
    entries.clear();
  }
}

/// The device cache, scoped to the signed-in user's subject. Tests override it.
final snapshotCacheProvider = Provider<SnapshotCache>((ref) {
  final tokens = ref.watch(tokenManagerProvider);
  return EncryptedSnapshotCache(
    root: getApplicationSupportDirectory,
    keys: const SecureCacheKeyStore(),
    user: () {
      final subject = tokens.claims['sub'];
      return subject is String ? subject : null;
    },
  );
});
