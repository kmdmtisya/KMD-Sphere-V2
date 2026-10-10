import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/auth/auth_controller.dart';
import '../../../core/data/json_reader.dart';
import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';

/// The signed-in user as the backend knows them (`GET /api/v1/me`).
@immutable
class Account {
  const Account({
    required this.id,
    required this.email,
    required this.baseCurrency,
  });

  factory Account.fromJson(JsonReader r) => Account(
    id: r.string('id'),
    email: r.stringOrNull('email'),
    baseCurrency: r.string('base_currency'),
  );

  final String id;
  final String? email;
  final String baseCurrency;
}

class AccountRepository {
  const AccountRepository(this._dio);

  final Dio _dio;

  Future<Account> me() async {
    try {
      final response = await _dio.get<Object?>('/api/v1/me');
      return Account.fromJson(JsonReader(response.data));
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }
}

final accountRepositoryProvider = Provider<AccountRepository>(
  (ref) => AccountRepository(ref.watch(apiClientProvider)),
);

/// The server's view of the account while signed in; null when signed out.
final currentAccountProvider = FutureProvider.autoDispose<Account?>((ref) {
  final auth = ref.watch(authControllerProvider);
  if (auth is! SignedIn) return null;
  return ref.watch(accountRepositoryProvider).me();
});
