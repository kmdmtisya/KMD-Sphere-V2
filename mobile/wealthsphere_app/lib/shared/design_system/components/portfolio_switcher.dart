import 'package:flutter/material.dart';

import '../../../l10n/generated/app_localizations.dart';
import '../formatting/formatting.dart';
import '../theme/wealth_typography.dart';
import '../tokens/tokens.dart';
import 'context_locale.dart';

/// A portfolio as the switcher shows it. Values are display strings' source data from the
/// backend; nothing is summed here.
@immutable
class PortfolioOption {
  const PortfolioOption({required this.id, required this.name, this.value});

  final String id;
  final String name;
  final Money? value;
}

/// Header button naming the current portfolio. Opens a bottom sheet with every portfolio plus the
/// consolidated view. `selectedId == null` means "all portfolios (consolidated)".
class PortfolioSwitcher extends StatelessWidget {
  const PortfolioSwitcher({
    required this.portfolios,
    required this.selectedId,
    required this.onSelected,
    this.consolidatedValue,
    super.key,
  });

  final List<PortfolioOption> portfolios;
  final String? selectedId;
  final ValueChanged<String?> onSelected;

  /// The backend-supplied total across portfolios.
  final Money? consolidatedValue;

  String _currentName(AppLocalizations l10n) {
    for (final p in portfolios) {
      if (p.id == selectedId) return p.name;
    }
    return l10n.allPortfolios;
  }

  Future<void> _open(BuildContext context) async {
    final result = await showModalBottomSheet<_Choice>(
      context: context,
      showDragHandle: true,
      isScrollControlled: true,
      builder: (_) => _PortfolioSheet(
        portfolios: portfolios,
        selectedId: selectedId,
        consolidatedValue: consolidatedValue,
      ),
    );
    if (result != null) onSelected(result.id);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final name = _currentName(l10n);
    return Semantics(
      button: true,
      label: l10n.portfolioSwitcherSpoken(name),
      excludeSemantics: true,
      onTap: () => _open(context),
      child: TextButton.icon(
        onPressed: () => _open(context),
        style: TextButton.styleFrom(
          minimumSize: const Size(
            AppTouchTarget.android,
            AppTouchTarget.android,
          ),
        ),
        icon: const Icon(Icons.keyboard_arrow_down_rounded),
        iconAlignment: IconAlignment.end,
        label: Text(name, maxLines: 1, overflow: TextOverflow.ellipsis),
      ),
    );
  }
}

class _Choice {
  const _Choice(this.id);
  final String? id;
}

class _PortfolioSheet extends StatelessWidget {
  const _PortfolioSheet({
    required this.portfolios,
    required this.selectedId,
    required this.consolidatedValue,
  });

  final List<PortfolioOption> portfolios;
  final String? selectedId;
  final Money? consolidatedValue;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final text = context.wealthText;
    final money = context.moneyFormatter;
    Widget tile(String? id, String title, Money? value) {
      final selected = id == selectedId;
      return Semantics(
        inMutuallyExclusiveGroup: true,
        checked: selected,
        child: ListTile(
          minVerticalPadding: AppSpacing.xs,
          title: Text(title),
          subtitle: value == null ? null : Text(money.format(value)),
          trailing: selected ? const Icon(Icons.check_rounded) : null,
          onTap: () => Navigator.of(context).pop(_Choice(id)),
        ),
      );
    }

    return SafeArea(
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsetsDirectional.symmetric(
                horizontal: AppSpacing.m,
              ),
              child: Text(l10n.selectPortfolio, style: text.title),
            ),
            tile(null, l10n.allPortfolios, consolidatedValue),
            for (final p in portfolios) tile(p.id, p.name, p.value),
          ],
        ),
      ),
    );
  }
}
