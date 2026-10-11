import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/more_repository.dart';
import '../domain/more_models.dart';

final netWorthDetailProvider = FutureProvider<NetWorthDetail>(
  (ref) => ref.watch(moreRepositoryProvider).netWorth(),
);

final incomeDetailProvider = FutureProvider<IncomeDetail>(
  (ref) => ref.watch(moreRepositoryProvider).income(),
);
