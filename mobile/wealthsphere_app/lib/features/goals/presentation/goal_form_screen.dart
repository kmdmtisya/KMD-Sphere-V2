import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/data/data_source_badge.dart';
import '../../../core/input/decimal_input.dart';
import '../../../l10n/generated/app_localizations.dart';
import '../../../shared/design_system/components/components.dart';
import '../../../shared/design_system/formatting/formatting.dart';
import '../../../shared/design_system/theme/theme.dart';
import '../../../shared/design_system/tokens/tokens.dart';
import '../../calculator/presentation/calculator_screen.dart'
    show frequencyLabel;
import '../../forecast/domain/forecast_models.dart';
import '../../portfolios/application/portfolio_providers.dart';
import '../application/goal_form.dart';
import '../application/goal_providers.dart';
import '../data/goal_repository.dart';
import '../domain/goal_models.dart';
import 'goal_labels.dart';

/// Adds a goal, or edits one when [goalId] is given. Every number is checked against the same
/// limits as the backend with a plain sentence next to the field. The person chooses every rate:
/// none is pre-filled or suggested.
class GoalFormScreen extends ConsumerWidget {
  const GoalFormScreen({this.goalId, this.onSaved, super.key});

  final String? goalId;

  /// Called with the saved goal.
  final void Function(GoalEntry entry)? onSaved;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    final editing = goalId != null;
    final title = editing ? l10n.goalFormEditTitle : l10n.goalFormAddTitle;
    final appBar = AppBar(
      title: Text(title),
      actions: const [
        DataSourceBadge(),
        SizedBox(width: AppSpacing.m),
      ],
    );
    if (!editing) {
      return Scaffold(
        appBar: appBar,
        body: _GoalForm(initial: const GoalDraft(), onSaved: onSaved),
      );
    }
    final entry = ref.watch(goalProvider(goalId!));
    return Scaffold(
      appBar: appBar,
      body: AsyncValueView<GoalEntry>(
        value: entry,
        onRetry: () => ref.invalidate(goalProvider(goalId!)),
        data: (e) => _GoalForm(
          editing: e.goal,
          initial: GoalDraft.from(e.goal, DecimalInput(context.formatLocale)),
          onSaved: onSaved,
        ),
      ),
    );
  }
}

class _GoalForm extends ConsumerStatefulWidget {
  const _GoalForm({required this.initial, this.editing, this.onSaved});

  final GoalDraft initial;
  final Goal? editing;
  final void Function(GoalEntry entry)? onSaved;

  @override
  ConsumerState<_GoalForm> createState() => _GoalFormState();
}

class _GoalFormState extends ConsumerState<_GoalForm> {
  late final TextEditingController _name = TextEditingController(
    text: widget.initial.name,
  );
  late final Map<GoalField, TextEditingController> _numbers = {
    GoalField.target: TextEditingController(text: widget.initial.target),
    GoalField.contribution: TextEditingController(
      text: widget.initial.contribution,
    ),
    GoalField.baseReturn: TextEditingController(
      text: widget.initial.baseReturn,
    ),
    GoalField.conservativeReturn: TextEditingController(
      text: widget.initial.conservativeReturn,
    ),
    GoalField.growthReturn: TextEditingController(
      text: widget.initial.growthReturn,
    ),
    GoalField.contributionGrowth: TextEditingController(
      text: widget.initial.contributionGrowth,
    ),
    GoalField.inflation: TextEditingController(text: widget.initial.inflation),
    GoalField.annualFee: TextEditingController(text: widget.initial.annualFee),
  };

  late GoalType _type = widget.initial.type;
  late DateTime? _date = widget.initial.targetDate;
  late bool _todaysMoney = widget.initial.targetInTodaysMoney;
  late String? _portfolioId = widget.initial.portfolioId;
  late Frequency _frequency = widget.initial.frequency;

  bool _submitted = false;
  Map<GoalField, GoalIssue> _issues = const {};
  bool _saving = false;
  String? _banner;
  bool _canRetry = false;

  @override
  void dispose() {
    _name.dispose();
    for (final c in _numbers.values) {
      c.dispose();
    }
    super.dispose();
  }

  DecimalInput get _input => DecimalInput(context.formatLocale);

  GoalDraft _draft() => GoalDraft(
    name: _name.text,
    type: _type,
    target: _numbers[GoalField.target]!.text,
    targetDate: _date,
    targetInTodaysMoney: _todaysMoney,
    portfolioId: _portfolioId,
    contribution: _numbers[GoalField.contribution]!.text,
    frequency: _frequency,
    baseReturn: _numbers[GoalField.baseReturn]!.text,
    conservativeReturn: _numbers[GoalField.conservativeReturn]!.text,
    growthReturn: _numbers[GoalField.growthReturn]!.text,
    contributionGrowth: _numbers[GoalField.contributionGrowth]!.text,
    inflation: _numbers[GoalField.inflation]!.text,
    annualFee: _numbers[GoalField.annualFee]!.text,
  );

  Future<List<String>> _otherNames() async {
    final all = await ref.read(goalsProvider.future);
    return [
      for (final e in all)
        if (e.goal.id != widget.editing?.id) e.goal.name,
    ];
  }

  /// Names of the other goals, read without waiting (empty until the list has loaded).
  List<String> get _knownOtherNames => [
    for (final e in ref.read(goalsProvider).value ?? const <GoalEntry>[])
      if (e.goal.id != widget.editing?.id) e.goal.name,
  ];

  GoalValidation _check() => validateGoal(
    _draft(),
    today: ref.read(goalsTodayProvider),
    input: _input,
    otherNames: _knownOtherNames,
  );

  void _changed(VoidCallback update) {
    setState(() {
      update();
      if (_submitted) _issues = _check().issues;
    });
  }

  Future<void> _save() async {
    final l10n = AppLocalizations.of(context);
    setState(() => _submitted = true);
    // Make sure the names of the other goals are known before judging a duplicate.
    await _otherNames().catchError((_) => <String>[]);
    if (!mounted) return;
    final result = _check();
    setState(() {
      _issues = result.issues;
      _banner = null;
    });
    final input = result.value;
    if (input == null) return;

    setState(() {
      _saving = true;
      _canRetry = false;
    });
    try {
      final repo = ref.read(goalRepositoryProvider);
      final entry = widget.editing == null
          ? await repo.create(input)
          : await repo.update(widget.editing!.id, input);
      refreshGoals(ref);
      if (!mounted) return;
      setState(() => _saving = false);
      ScaffoldMessenger.of(context)
        ..hideCurrentSnackBar()
        ..showSnackBar(SnackBar(content: Text(l10n.goalFormSaved)));
      widget.onSaved?.call(entry);
    } on GoalRuleException catch (e) {
      if (!mounted) return;
      setState(() {
        _saving = false;
        switch (e.rule) {
          case GoalRule.nameTaken:
            _issues = {
              ..._issues,
              GoalField.name: const GoalIssue(GoalIssueKind.nameTaken),
            };
          case GoalRule.tooMany:
            _banner = l10n.goalErrTooMany;
          case GoalRule.notFound:
            _banner = l10n.goalErrNotFound;
        }
      });
    } on Object {
      if (!mounted) return;
      setState(() {
        _saving = false;
        _banner = l10n.goalFormSaveFailed;
        _canRetry = true;
      });
    }
  }

  Future<void> _pickDate() async {
    final today = ref.read(goalsTodayProvider);
    final first = DateTime(today.year, today.month, today.day + 1);
    final last = DateTime(
      today.year + GoalLimits.maxYearsAhead,
      today.month,
      today.day,
    );
    final initial =
        _date != null && !_date!.isBefore(first) && !_date!.isAfter(last)
        ? _date!
        : first;
    final picked = await showDatePicker(
      context: context,
      initialDate: initial,
      firstDate: first,
      lastDate: last,
    );
    if (picked != null && mounted) _changed(() => _date = picked);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final locale = context.formatLocale;
    final portfolios = ref.watch(portfolioListProvider).value ?? const [];
    // Watching keeps the other goals' names loaded, for the duplicate-name check.
    ref.watch(goalsProvider);

    String? error(GoalField f) =>
        _issues[f] == null ? null : goalIssueText(l10n, _issues[f]!, locale);

    Widget number(
      GoalField field,
      String label, {
      bool negative = false,
      TextInputAction action = TextInputAction.next,
    }) {
      final limit = GoalLimits.of(field);
      return TextField(
        controller: _numbers[field],
        decoration: InputDecoration(
          labelText: label,
          errorText: error(field),
          errorMaxLines: 3,
        ),
        keyboardType: TextInputType.numberWithOptions(
          decimal: true,
          signed: negative,
        ),
        textInputAction: action,
        inputFormatters: [
          _input.formatter(
            maxFractionDigits: limit.fractionDigits,
            allowNegative: negative,
          ),
        ],
        onChanged: (_) => _changed(() {}),
      );
    }

    const gap = SizedBox(height: AppSpacing.m);
    final text = context.wealthText;
    return ListView(
      padding: const EdgeInsetsDirectional.all(AppSpacing.m),
      children: [
        if (_banner != null) ...[
          Semantics(
            liveRegion: true,
            child: StatusBanner(
              icon: Icons.error_outline_rounded,
              message: _banner!,
              actionLabel: _canRetry ? l10n.addTxRetry : null,
              onAction: _canRetry ? _save : null,
            ),
          ),
          gap,
        ],
        if (_issues.isNotEmpty) ...[
          Semantics(
            liveRegion: true,
            child: StatusBanner(
              icon: Icons.error_outline_rounded,
              message: l10n.goalFormFixFields(_issues.length),
            ),
          ),
          gap,
        ],
        TextField(
          controller: _name,
          maxLength: GoalLimits.maxNameLength + 20,
          decoration: InputDecoration(
            labelText: l10n.goalFormName,
            errorText: error(GoalField.name),
            errorMaxLines: 3,
          ),
          textInputAction: TextInputAction.next,
          onChanged: (_) => _changed(() {}),
        ),
        gap,
        DropdownButtonFormField<GoalType>(
          initialValue: _type,
          isExpanded: true,
          decoration: InputDecoration(labelText: l10n.goalFormType),
          items: [
            for (final t in GoalType.values)
              DropdownMenuItem(value: t, child: Text(goalTypeLabel(l10n, t))),
          ],
          onChanged: (v) {
            if (v != null) _changed(() => _type = v);
          },
        ),
        gap,
        number(GoalField.target, l10n.goalFormTarget),
        gap,
        _DateField(
          label: l10n.goalFormTargetDate,
          hint: l10n.addTxDateHint,
          value: _date,
          error: error(GoalField.targetDate),
          onTap: _pickDate,
        ),
        gap,
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: Text(l10n.goalFormTodaysMoney),
          subtitle: Text(l10n.goalFormTodaysMoneyHelp),
          value: _todaysMoney,
          onChanged: (v) => _changed(() => _todaysMoney = v),
        ),
        gap,
        DropdownButtonFormField<String?>(
          key: ValueKey('funding-$_portfolioId-${portfolios.length}'),
          initialValue: _portfolioId,
          isExpanded: true,
          decoration: InputDecoration(labelText: l10n.goalFormFunding),
          items: [
            DropdownMenuItem<String?>(child: Text(l10n.goalFundedAll)),
            for (final p in portfolios)
              DropdownMenuItem<String?>(value: p.id, child: Text(p.name)),
          ],
          onChanged: (v) => _changed(() => _portfolioId = v),
        ),
        gap,
        Semantics(
          header: true,
          child: Text(l10n.goalFormAssumptionsHeading, style: text.title),
        ),
        Text(
          l10n.goalFormAssumptionsNote,
          style: text.caption.copyWith(color: context.wealthColors.textMuted),
        ),
        gap,
        number(GoalField.contribution, l10n.goalFormContribution),
        gap,
        DropdownButtonFormField<Frequency>(
          initialValue: _frequency,
          isExpanded: true,
          decoration: InputDecoration(labelText: l10n.goalFormFrequency),
          items: [
            for (final f in Frequency.values)
              DropdownMenuItem(value: f, child: Text(frequencyLabel(l10n, f))),
          ],
          onChanged: (v) {
            if (v != null) _changed(() => _frequency = v);
          },
        ),
        gap,
        number(GoalField.baseReturn, l10n.goalFormBaseReturn, negative: true),
        gap,
        number(
          GoalField.conservativeReturn,
          l10n.goalFormConservative,
          negative: true,
        ),
        gap,
        number(
          GoalField.growthReturn,
          l10n.goalFormGrowthReturn,
          negative: true,
        ),
        gap,
        number(GoalField.contributionGrowth, l10n.goalFormContributionGrowth),
        gap,
        number(GoalField.inflation, l10n.goalFormInflation),
        gap,
        number(
          GoalField.annualFee,
          l10n.goalFormFee,
          action: TextInputAction.done,
        ),
        gap,
        Text(
          l10n.goalFormDemoNote,
          style: text.caption.copyWith(color: context.wealthColors.textMuted),
        ),
        gap,
        FilledButton(
          onPressed: _saving ? null : _save,
          child: Text(_saving ? l10n.goalFormSaving : l10n.goalFormSave),
        ),
      ],
    );
  }
}

/// A read-only field that opens the date picker, laid out like the text fields.
class _DateField extends StatelessWidget {
  const _DateField({
    required this.label,
    required this.hint,
    required this.value,
    required this.error,
    required this.onTap,
  });

  final String label;
  final String hint;
  final DateTime? value;
  final String? error;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final shown = value == null
        ? hint
        : DateLabels.date(value!, locale: context.formatLocale);
    return InkWell(
      onTap: onTap,
      child: ConstrainedBox(
        constraints: const BoxConstraints(minHeight: AppTouchTarget.android),
        child: InputDecorator(
          decoration: InputDecoration(
            labelText: label,
            errorText: error,
            errorMaxLines: 3,
            suffixIcon: const Icon(Icons.calendar_today_rounded),
          ),
          child: Text(
            shown,
            style: value == null
                ? context.wealthText.body.copyWith(
                    color: context.wealthColors.textMuted,
                  )
                : context.wealthText.body,
          ),
        ),
      ),
    );
  }
}
