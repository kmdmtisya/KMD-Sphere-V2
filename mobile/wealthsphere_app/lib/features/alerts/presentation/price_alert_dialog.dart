import 'package:decimal/decimal.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/input/decimal_input.dart';
import '../../../l10n/generated/app_localizations.dart';
import '../../../shared/design_system/components/components.dart';
import '../../../shared/design_system/formatting/money.dart';
import '../../../shared/design_system/tokens/tokens.dart';
import '../../investments/domain/investment_models.dart';
import '../application/alerts_providers.dart';
import '../data/alerts_repository.dart';
import '../domain/alert_models.dart';

/// Sets a price alert on one investment: above or below a price in the asset's own currency.
/// The server checks it against stored prices and fires it once; it never trades.
class PriceAlertDialog extends ConsumerStatefulWidget {
  const PriceAlertDialog({
    required this.assetKey,
    required this.detail,
    super.key,
  });

  final String assetKey;
  final InvestmentDetail detail;

  @override
  ConsumerState<PriceAlertDialog> createState() => _PriceAlertDialogState();
}

class _PriceAlertDialogState extends ConsumerState<PriceAlertDialog> {
  final _price = TextEditingController();
  AlertType _type = AlertType.priceAbove;
  String? _error;
  bool _saving = false;

  @override
  void dispose() {
    _price.dispose();
    super.dispose();
  }

  Future<void> _save(AppLocalizations l10n) async {
    final value = DecimalInput(context.formatLocale).parse(_price.text);
    if (value == null || value <= Decimal.zero) {
      setState(() => _error = l10n.alertPriceInvalid);
      return;
    }
    setState(() {
      _error = null;
      _saving = true;
    });
    try {
      await ref
          .read(alertRepositoryProvider)
          .createPriceAlert(
            assetKey: widget.assetKey,
            type: _type,
            threshold: Money(value, widget.detail.currency),
          );
      ref.invalidate(alertsProvider);
      if (mounted) Navigator.of(context).pop(true);
    } on Object {
      if (mounted) {
        setState(() {
          _saving = false;
          _error = l10n.alertSaveFailed;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final current = widget.detail.price;
    return AlertDialog(
      title: Text(l10n.alertSetPriceFor(widget.detail.name)),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SegmentedButton<AlertType>(
              segments: [
                ButtonSegment(
                  value: AlertType.priceAbove,
                  label: Text(l10n.alertAbove),
                ),
                ButtonSegment(
                  value: AlertType.priceBelow,
                  label: Text(l10n.alertBelow),
                ),
              ],
              selected: {_type},
              onSelectionChanged: (s) => setState(() => _type = s.first),
            ),
            const SizedBox(height: AppSpacing.s),
            TextField(
              controller: _price,
              keyboardType: const TextInputType.numberWithOptions(
                decimal: true,
              ),
              decoration: InputDecoration(
                labelText: l10n.alertPriceLabel(widget.detail.currency),
                errorText: _error,
                helperText: current == null
                    ? l10n.investNoPriceYet
                    : l10n.alertCurrentPrice(
                        context.moneyFormatter.format(current),
                      ),
                helperMaxLines: 2,
              ),
            ),
            const SizedBox(height: AppSpacing.s),
            Text(l10n.alertNote, style: Theme.of(context).textTheme.bodySmall),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: _saving ? null : () => Navigator.of(context).pop(false),
          child: Text(l10n.cancel),
        ),
        FilledButton(
          onPressed: _saving ? null : () => _save(l10n),
          child: Text(l10n.alertSave),
        ),
      ],
    );
  }
}
