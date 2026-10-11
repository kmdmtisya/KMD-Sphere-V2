import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../shared/design_system/components/components.dart';
import '../../../shared/domain/wealth_models.dart';
import '../application/portfolio_providers.dart';

/// The header control that names the selected portfolio (or "all portfolios") and switches it.
/// The selection is shared by every screen that follows it (Portfolio, holdings, transactions,
/// Portfolio Doctor).
class PortfolioScopeSwitcher extends ConsumerWidget {
  const PortfolioScopeSwitcher({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final selectedId = ref.watch(selectedPortfolioIdProvider);
    final list = ref.watch(portfolioListProvider);
    final consolidated = ref
        .watch(portfolioSummaryProvider(PortfolioRef.consolidatedId))
        .value;
    return PortfolioSwitcher(
      portfolios: [
        for (final p in list.value ?? const <PortfolioRef>[])
          PortfolioOption(
            id: p.id,
            name: p.name,
            value: ref.watch(portfolioSummaryProvider(p.id)).value?.value,
          ),
      ],
      selectedId: selectedId == PortfolioRef.consolidatedId ? null : selectedId,
      consolidatedValue: consolidated?.value,
      onSelected: (id) => ref
          .read(selectedPortfolioIdProvider.notifier)
          .select(id ?? PortfolioRef.consolidatedId),
    );
  }
}
