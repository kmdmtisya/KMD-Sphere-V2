import 'dart:async';

import 'package:decimal/decimal.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../app/app_routes.dart';
import '../../../core/data/demo_support.dart';
import '../../../core/input/decimal_input.dart';
import '../../../l10n/generated/app_localizations.dart';
import '../../../shared/design_system/components/components.dart';
import '../../../shared/design_system/formatting/currency_info.dart';
import '../../../shared/design_system/formatting/number_style.dart';
import '../../../shared/design_system/theme/theme.dart';
import '../../../shared/design_system/tokens/tokens.dart';
import '../../forecast/data/forecast_repository.dart';
import '../../forecast/domain/forecast_models.dart';
import '../application/calculator_providers.dart';
import '../domain/forecast_input_limits.dart';

/// Text of a validation [issue], in the user's language and number format.
String issueMessage(AppLocalizations l10n, InputIssue issue, String locale) {
  String number(Decimal? v) {
    if (v == null) return '';
    final text = NumberStyle.forLocale(locale).renderUnsigned(v.abs(), 0);
    return v.sign < 0 ? '-$text' : text;
  }

  return switch (issue.kind) {
    IssueKind.required => l10n.inputRequired,
    IssueKind.invalid => l10n.inputInvalid,
    IssueKind.notWhole => l10n.inputWholeNumber,
    IssueKind.tooLow => l10n.inputTooLow(number(issue.bound)),
    IssueKind.tooHigh => l10n.inputTooHigh(number(issue.bound)),
    IssueKind.tooManyDecimals => l10n.inputTooManyDecimals(number(issue.bound)),
    IssueKind.conservativeAboveBase => l10n.inputConservativeAboveBase,
    IssueKind.growthBelowBase => l10n.inputGrowthBelowBase,
  };
}

String frequencyLabel(AppLocalizations l10n, Frequency f) => switch (f) {
  Frequency.monthly => l10n.calcFrequencyMonthly,
  Frequency.quarterly => l10n.calcFrequencyQuarterly,
  Frequency.yearly => l10n.calcFrequencyYearly,
};

/// The Compounding Calculator. It only collects and validates inputs; the projection is computed
/// by the backend (`ForecastRepository.compound`) and shown on the Forecast screen.
class CalculatorScreen extends ConsumerStatefulWidget {
  const CalculatorScreen({super.key});

  @override
  ConsumerState<CalculatorScreen> createState() => _CalculatorScreenState();
}

const Set<CalculatorField> _advancedFields = {
  CalculatorField.inflation,
  CalculatorField.annualFee,
  CalculatorField.conservativeReturn,
  CalculatorField.growthReturn,
};

class _CalculatorScreenState extends ConsumerState<CalculatorScreen> {
  final _formKey = GlobalKey<FormState>();
  final Map<CalculatorField, TextEditingController> _controllers = {};
  final Map<CalculatorField, FocusNode> _focus = {
    for (final f in CalculatorField.values) f: FocusNode(),
  };
  final _advanced = ExpansibleController();
  bool _loading = false;
  bool _failed = false;
  bool _showFixHint = false;
  String _locale = 'en';
  DecimalInput _input = DecimalInput('en');
  CalculatorInputs _defaults = CalculatorInputs.defaults('en');

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final locale = Localizations.localeOf(context).toString();
    if (_controllers.isNotEmpty && locale == _locale) return;
    _locale = locale;
    _input = DecimalInput(locale);
    _defaults = CalculatorInputs.defaults(locale);
    final inputs = ref.read(calculatorInputsProvider) ?? _defaults;
    for (final f in CalculatorField.values) {
      _controllers[f] ??= TextEditingController(text: inputs.text(f));
    }
  }

  @override
  void dispose() {
    _advanced.dispose();
    for (final c in _controllers.values) {
      c.dispose();
    }
    for (final n in _focus.values) {
      n.dispose();
    }
    super.dispose();
  }

  String? _validate(CalculatorField field, String? text) {
    final l10n = AppLocalizations.of(context);
    final issue =
        ForecastInputLimits.validate(
          field,
          text ?? '',
          _input,
          required: field != CalculatorField.contributionGrowth,
        ) ??
        ForecastInputLimits.validateOrdering(
          field,
          _input.parse(_controllers[CalculatorField.conservativeReturn]!.text),
          _input.parse(_controllers[CalculatorField.annualReturn]!.text),
          _input.parse(_controllers[CalculatorField.growthReturn]!.text),
        );
    return issue == null ? null : issueMessage(l10n, issue, _locale);
  }

  Future<void> _calculate() async {
    setState(() {
      _failed = false;
      _showFixHint = false;
    });
    // Show every message, but decide validity from all fields directly so nothing collapsed or
    // offscreen can slip through.
    _formKey.currentState!.validate();
    final invalid = [
      for (final f in CalculatorField.values)
        if (_validate(f, _controllers[f]!.text) != null) f,
    ];
    if (invalid.isNotEmpty) {
      setState(() => _showFixHint = true);
      if (_advancedFields.contains(invalid.first)) _advanced.expand();
      _focus[invalid.first]!.requestFocus();
      return;
    }
    FocusScope.of(context).unfocus();
    final inputs = ref.read(calculatorInputsProvider) ?? _defaults;
    // Empty optional fields mean zero.
    final request =
        inputs.toRequest(_input) ??
        inputs
            .copyWith(
              texts: {...inputs.texts, CalculatorField.contributionGrowth: '0'},
            )
            .toRequest(_input);
    if (request == null) return;
    setState(() => _loading = true);
    try {
      final response = await ref
          .read(forecastRepositoryProvider)
          .compound(request);
      ref
          .read(forecastResultProvider.notifier)
          .set(ForecastResult(request: request, response: response));
      if (mounted) unawaited(context.push(AppRoutes.forecast));
    } on DataLoadException {
      if (mounted) setState(() => _failed = true);
    } on Object {
      if (mounted) setState(() => _failed = true);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final inputs = ref.watch(calculatorInputsProvider) ?? _defaults;
    final notifier = ref.read(calculatorInputsProvider.notifier);
    final symbol =
        CurrencyInfo.of(ForecastInputLimits.currency).symbol ??
        ForecastInputLimits.currency;
    final text = context.wealthText;

    Widget field(
      CalculatorField f,
      String label, {
      String? prefix,
      String? suffix,
      TextInputAction action = TextInputAction.next,
      String? helper,
    }) {
      final limit = ForecastInputLimits.of(f);
      return Padding(
        padding: const EdgeInsetsDirectional.only(bottom: AppSpacing.s),
        child: TextFormField(
          key: ValueKey('field-${f.name}'),
          controller: _controllers[f],
          focusNode: _focus[f],
          autovalidateMode: AutovalidateMode.onUserInteraction,
          validator: (v) => _validate(f, v),
          onChanged: (v) {
            notifier.setText(f, v, base: _defaults);
            setState(() => _showFixHint = false);
          },
          textInputAction: action,
          keyboardType: TextInputType.numberWithOptions(
            decimal: limit.fractionDigits > 0,
            signed: limit.allowsNegative,
          ),
          inputFormatters: [
            _input.formatter(
              maxFractionDigits: limit.fractionDigits,
              allowNegative: limit.allowsNegative,
            ),
          ],
          decoration: InputDecoration(
            labelText: label,
            prefixText: prefix,
            suffixText: suffix,
            helperText: helper,
            helperMaxLines: 2,
          ),
          onFieldSubmitted: (_) {
            if (action == TextInputAction.done) unawaited(_calculate());
          },
        ),
      );
    }

    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.calculatorTitle),
        actions: const [
          DemoBadge(),
          SizedBox(width: AppSpacing.m),
        ],
      ),
      body: Column(
        children: [
          Expanded(
            child: Form(
              key: _formKey,
              // Not a lazy list: every field must stay mounted so Form.validate() sees it.
              child: SingleChildScrollView(
                keyboardDismissBehavior:
                    ScrollViewKeyboardDismissBehavior.onDrag,
                padding: const EdgeInsetsDirectional.all(AppSpacing.m),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    field(
                      CalculatorField.initialInvestment,
                      l10n.calcInitialInvestment,
                      prefix: '$symbol ',
                    ),
                    field(
                      CalculatorField.monthlyContribution,
                      l10n.calcMonthlyContribution,
                      prefix: '$symbol ',
                    ),
                    field(
                      CalculatorField.annualReturn,
                      l10n.calcExpectedReturn,
                      suffix: '%',
                      helper: l10n.calcNegativeNote,
                    ),
                    field(CalculatorField.years, l10n.calcYears),
                    field(
                      CalculatorField.contributionGrowth,
                      l10n.calcContributionGrowth,
                      suffix: '%',
                      action: TextInputAction.done,
                    ),
                    Theme(
                      data: Theme.of(context)
                          .copyWith(dividerColor: Colors.transparent),
                      child: ExpansionTile(
                        key: const ValueKey('advanced'),
                        controller: _advanced,
                        // Collapsed fields stay mounted so they are still validated.
                        maintainState: true,
                        tilePadding: EdgeInsets.zero,
                        title: Text(l10n.calcAdvanced, style: text.title),
                        children: [
                          field(
                            CalculatorField.inflation,
                            l10n.calcInflation,
                            suffix: '%',
                          ),
                          field(
                            CalculatorField.annualFee,
                            l10n.calcFee,
                            suffix: '%',
                          ),
                          _FrequencyPicker(
                            label: l10n.calcCompounding,
                            value: inputs.compounding,
                            onChanged: (f) =>
                                notifier.setCompounding(f, base: _defaults),
                          ),
                          _FrequencyPicker(
                            label: l10n.calcContributionFrequency,
                            value: inputs.contribution,
                            onChanged: (f) =>
                                notifier.setContribution(f, base: _defaults),
                          ),
                          const SizedBox(height: AppSpacing.s),
                          Align(
                            alignment: AlignmentDirectional.centerStart,
                            child: Text(
                              l10n.calcYourAssumptions,
                              style: text.title,
                            ),
                          ),
                          const SizedBox(height: AppSpacing.xs),
                          field(
                            CalculatorField.conservativeReturn,
                            l10n.calcConservativeReturn,
                            suffix: '%',
                          ),
                          field(
                            CalculatorField.growthReturn,
                            l10n.calcGrowthReturn,
                            suffix: '%',
                            action: TextInputAction.done,
                          ),
                        ],
                      ),
                    ),
                    if (_showFixHint)
                      Padding(
                        padding: const EdgeInsetsDirectional.only(
                          bottom: AppSpacing.s,
                        ),
                        child: Semantics(
                          liveRegion: true,
                          child: Text(
                            l10n.calcFixErrors,
                            style: text.label.copyWith(
                              color: context.wealthColors.negativeText,
                            ),
                          ),
                        ),
                      ),
                    if (_failed)
                      Padding(
                        padding: const EdgeInsetsDirectional.only(
                          bottom: AppSpacing.s,
                        ),
                        child: Semantics(
                          liveRegion: true,
                          child: Text(
                            l10n.calcFailed,
                            style: text.label.copyWith(
                              color: context.wealthColors.negativeText,
                            ),
                          ),
                        ),
                      ),
                    FilledButton(
                      key: const ValueKey('calculate'),
                      onPressed: _loading ? null : _calculate,
                      child: _loading
                          ? Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                const SizedBox(
                                  width: 18,
                                  height: 18,
                                  child: CircularProgressIndicator(
                                    strokeWidth: 2,
                                  ),
                                ),
                                const SizedBox(width: AppSpacing.xs),
                                Flexible(child: Text(l10n.calcCalculating)),
                              ],
                            )
                          : Text(_failed ? l10n.retry : l10n.calcCalculate),
                    ),
                  ],
                ),
              ),
            ),
          ),
          _Footnote(text: l10n.calcFootnote),
        ],
      ),
    );
  }
}

class _FrequencyPicker extends StatelessWidget {
  const _FrequencyPicker({
    required this.label,
    required this.value,
    required this.onChanged,
  });

  final String label;
  final Frequency value;
  final ValueChanged<Frequency> onChanged;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return Padding(
      padding: const EdgeInsetsDirectional.only(bottom: AppSpacing.s),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: context.wealthText.label),
          const SizedBox(height: AppSpacing.xxs),
          SegmentedButton<Frequency>(
            showSelectedIcon: false,
            segments: [
              for (final f in Frequency.values)
                ButtonSegment(value: f, label: Text(frequencyLabel(l10n, f))),
            ],
            selected: {value},
            onSelectionChanged: (s) => onChanged(s.first),
          ),
        ],
      ),
    );
  }
}

/// Always visible, even with the keyboard open: projections are not promises.
class _Footnote extends StatelessWidget {
  const _Footnote({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    final colors = context.wealthColors;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: colors.surface,
        border: Border(top: BorderSide(color: colors.divider)),
      ),
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsetsDirectional.symmetric(
            horizontal: AppSpacing.m,
            vertical: AppSpacing.xs,
          ),
          child: Row(
            children: [
              Icon(
                Icons.info_outline_rounded,
                size: 16,
                color: colors.textMuted,
              ),
              const SizedBox(width: AppSpacing.xs),
              Expanded(
                child: Text(
                  text,
                  style: context.wealthText.caption.copyWith(
                    color: colors.textMuted,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
