import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../app/app_routes.dart';
import '../../../core/connectivity/connectivity.dart';
import '../../../l10n/generated/app_localizations.dart';
import '../../../shared/design_system/components/components.dart';
import '../../../shared/design_system/theme/theme.dart';
import '../../../shared/design_system/tokens/tokens.dart';
import '../../../shared/domain/chart_mapping.dart';
import '../../../shared/domain/wealth_models.dart';
import '../../copilot/data/copilot_repository.dart';
import '../../copilot/domain/chat_models.dart';
import '../../portfolios/application/portfolio_providers.dart';
import '../application/copilot_controller.dart';

final _copilotIntroProvider = FutureProvider<CopilotIntro>(
  (ref) => ref.watch(copilotRepositoryProvider).intro(),
);

final _suggestionsProvider = FutureProvider<List<String>>(
  (ref) => ref.watch(copilotRepositoryProvider).suggestedQuestions(),
);

String sectionHeading(AppLocalizations l10n, SectionKind kind) =>
    switch (kind) {
      SectionKind.observed => l10n.aiSectionObserved,
      SectionKind.calculated => l10n.aiSectionCalculated,
      SectionKind.assumption => l10n.aiSectionAssumption,
      SectionKind.interpretation => l10n.aiSectionInterpretation,
    };

/// AI Wealth: a conversation with the Copilot. Every word of every answer comes from the
/// repository (demo scripts now, the AI orchestrator later); nothing is advice written in Dart.
///
/// [scope] comes from the route (`/ai?scope=...`) and can be changed or removed by the user; it is
/// sent with each question, and the server enforces what it may access.
class AiWealthScreen extends ConsumerStatefulWidget {
  const AiWealthScreen({this.scope, super.key});

  final AiScope? scope;

  @override
  ConsumerState<AiWealthScreen> createState() => _AiWealthScreenState();
}

class _AiWealthScreenState extends ConsumerState<AiWealthScreen> {
  AiScope? _scope;

  @override
  void initState() {
    super.initState();
    _scope = widget.scope;
  }

  @override
  void didUpdateWidget(AiWealthScreen old) {
    super.didUpdateWidget(old);
    if (old.scope != widget.scope) _scope = widget.scope;
  }

  void _ask(String question) {
    final l10n = AppLocalizations.of(context);
    ref
        .read(copilotControllerProvider.notifier)
        .ask(question, scope: _scope, failureMessage: l10n.aiFailedGeneric);
  }

  void _retry(int index) {
    final l10n = AppLocalizations.of(context);
    ref
        .read(copilotControllerProvider.notifier)
        .retry(index, scope: _scope, failureMessage: l10n.aiFailedGeneric);
  }

  Future<void> _chooseScope() async {
    final l10n = AppLocalizations.of(context);
    final portfolios = ref.read(portfolioListProvider).value ?? const [];
    final options = <(AiScope?, String)>[
      (null, l10n.aiScopeAll),
      for (final p in portfolios)
        (AiScope(AiScopeKind.portfolio, p.id), p.name),
      if (widget.scope != null && widget.scope!.kind != AiScopeKind.portfolio)
        (widget.scope, _scopeLabel(l10n, widget.scope, portfolios)),
    ];
    final picked = await showModalBottomSheet<(AiScope?,)>(
      context: context,
      showDragHandle: true,
      builder: (context) => SafeArea(
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Padding(
                padding: const EdgeInsetsDirectional.symmetric(
                  horizontal: AppSpacing.m,
                ),
                child: Text(
                  l10n.aiScopeSheetTitle,
                  style: context.wealthText.title,
                ),
              ),
              for (final (scope, label) in options)
                Semantics(
                  inMutuallyExclusiveGroup: true,
                  checked: scope == _scope,
                  child: ListTile(
                    title: Text(label),
                    trailing: scope == _scope
                        ? const Icon(Icons.check_rounded)
                        : null,
                    onTap: () => Navigator.of(context).pop((scope,)),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
    if (picked != null && mounted) setState(() => _scope = picked.$1);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final state = ref.watch(copilotControllerProvider);
    final online = ref.watch(onlineProvider);
    final portfolios = ref.watch(portfolioListProvider).value ?? const [];

    // Announce the end of an answer once, not every streamed piece.
    ref.listen(copilotControllerProvider, (previous, next) {
      if (previous?.streaming == true &&
          !next.streaming &&
          next.turns.isNotEmpty) {
        final last = next.turns.last;
        final message = last.failed
            ? l10n.aiAnswerFailed
            : last.stopped
            ? l10n.aiAnswerStopped
            : l10n.aiAnswerReady;
        SemanticsService.sendAnnouncement(
          View.of(context),
          message,
          Directionality.of(context),
        );
      }
    });

    // Small screens and large text: only the composer stays pinned; the context chip and the
    // footer scroll with the conversation so nothing overflows.
    final compact =
        MediaQuery.textScalerOf(context).scale(1) > 1.3 ||
        MediaQuery.sizeOf(context).height < 600;
    final chip = Align(
      alignment: AlignmentDirectional.centerStart,
      child: InputChip(
        avatar: const Icon(Icons.filter_center_focus_rounded, size: 18),
        label: Text(
          l10n.aiContextLabel(_scopeLabel(l10n, _scope, portfolios)),
          overflow: TextOverflow.ellipsis,
        ),
        tooltip: l10n.aiChangeScope,
        onPressed: state.streaming ? null : _chooseScope,
        onDeleted: _scope == null || state.streaming
            ? null
            : () => setState(() => _scope = null),
        deleteButtonTooltipMessage: l10n.aiRemoveScope,
      ),
    );
    final footer = _Footer(text: l10n.aiFooter);

    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.aiTitle),
        // Header slot: Opportunities and Portfolio Doctor entries arrive at gate 3.
        actions: const [
          DemoBadge(),
          SizedBox(width: AppSpacing.m),
        ],
      ),
      body: Column(
        children: [
          if (!online) const OfflineBanner(),
          Expanded(
            child: ListView(
              padding: const EdgeInsetsDirectional.all(AppSpacing.m),
              children: [
                if (compact) ...[chip, const SizedBox(height: AppSpacing.s)],
                if (state.turns.isEmpty)
                  _EmptyConversation(onAsk: online ? _ask : null)
                else
                  for (var i = 0; i < state.turns.length; i++)
                    _TurnView(
                      turn: state.turns[i],
                      streaming: state.streaming && i == state.turns.length - 1,
                      onRetry: online && !state.streaming
                          ? () => _retry(i)
                          : null,
                    ),
                if (compact) footer,
              ],
            ),
          ),
          if (!compact)
            Padding(
              padding: const EdgeInsetsDirectional.symmetric(
                horizontal: AppSpacing.s,
              ),
              child: chip,
            ),
          if (!online)
            Padding(
              padding: const EdgeInsetsDirectional.symmetric(
                horizontal: AppSpacing.m,
              ),
              child: Text(
                l10n.aiOfflineComposer,
                style: context.wealthText.caption,
              ),
            ),
          AIChatComposer(
            enabled: online,
            streaming: state.streaming,
            onSend: _ask,
            onStop: ref.read(copilotControllerProvider.notifier).stop,
          ),
          if (!compact) footer,
        ],
      ),
    );
  }
}

String _scopeLabel(
  AppLocalizations l10n,
  AiScope? scope,
  List<PortfolioRef> portfolios,
) {
  if (scope == null) return l10n.aiScopeAll;
  switch (scope.kind) {
    case AiScopeKind.portfolio:
      if (scope.id == PortfolioRef.consolidatedId) return l10n.aiScopeAll;
      for (final p in portfolios) {
        if (p.id == scope.id) return p.name;
      }
      return l10n.aiScopePortfolioUnknown(scope.id);
    case AiScopeKind.forecast:
      return l10n.aiScopeForecast;
    case AiScopeKind.goal:
      return l10n.aiScopeGoal(scope.id);
  }
}

class _EmptyConversation extends ConsumerWidget {
  const _EmptyConversation({required this.onAsk});

  /// Null when asking is not possible (offline).
  final ValueChanged<String>? onAsk;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    final text = context.wealthText;
    final intro = ref.watch(_copilotIntroProvider);
    final suggestions = ref.watch(_suggestionsProvider);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(
          Icons.auto_awesome_rounded,
          size: 40,
          color: context.wealthColors.primary,
        ),
        const SizedBox(height: AppSpacing.s),
        if (intro.value case final i?) ...[
          Text(i.intro, style: text.title),
          const SizedBox(height: AppSpacing.s),
          StatusBanner(icon: Icons.science_outlined, message: i.notice),
        ],
        const SizedBox(height: AppSpacing.m),
        Text(l10n.aiSuggestionsTitle, style: text.label),
        const SizedBox(height: AppSpacing.xs),
        AsyncValueView<List<String>>(
          value: suggestions,
          onRetry: () => ref.invalidate(_suggestionsProvider),
          data: (items) => Wrap(
            spacing: AppSpacing.xs,
            runSpacing: AppSpacing.xs,
            children: [
              for (final q in items)
                ActionChip(
                  label: Text(q),
                  onPressed: onAsk == null ? null : () => onAsk!(q),
                ),
            ],
          ),
        ),
      ],
    );
  }
}

class _TurnView extends StatelessWidget {
  const _TurnView({
    required this.turn,
    required this.streaming,
    required this.onRetry,
  });

  final ChatTurn turn;
  final bool streaming;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final colors = context.wealthColors;
    final text = context.wealthText;
    return Padding(
      padding: const EdgeInsetsDirectional.only(bottom: AppSpacing.m),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // The user's question.
          Align(
            alignment: AlignmentDirectional.centerEnd,
            child: Semantics(
              label: '${l10n.aiYou}: ${turn.question}',
              excludeSemantics: true,
              container: true,
              child: Container(
                constraints: const BoxConstraints(maxWidth: 520),
                padding: const EdgeInsetsDirectional.all(AppSpacing.s),
                decoration: BoxDecoration(
                  color: colors.primary,
                  borderRadius: AppRadii.mediumRadius,
                ),
                child: Text(
                  turn.question,
                  style: text.body.copyWith(color: colors.onPrimary),
                ),
              ),
            ),
          ),
          const SizedBox(height: AppSpacing.s),
          if (turn.refused)
            _RefusalCard(text: turn.refusal!)
          else
            WealthCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (streaming &&
                      turn.progress.isNotEmpty &&
                      turn.sections.isEmpty)
                    _Progress(text: turn.progress.last.text),
                  for (final section in turn.sections) ...[
                    Text(
                      sectionHeading(l10n, section.kind),
                      style: text.label.copyWith(color: colors.primary),
                    ),
                    const SizedBox(height: AppSpacing.xxs),
                    Text(section.text, style: text.body),
                    const SizedBox(height: AppSpacing.s),
                  ],
                  if (streaming && turn.sections.isNotEmpty)
                    const LinearProgressIndicator(minHeight: 2),
                  if (turn.sources.isNotEmpty) ...[
                    Text(l10n.aiSourcesTitle, style: text.caption),
                    Wrap(
                      spacing: AppSpacing.xs,
                      children: [
                        for (final s in turn.sources)
                          EvidenceSourceChip(source: s.toView()),
                      ],
                    ),
                    DataAsOfLabel(
                      asOf: turn.sources
                          .map((s) => s.asOf)
                          .reduce((a, b) => a.isAfter(b) ? a : b),
                    ),
                  ],
                  if (turn.stopped)
                    Text(
                      l10n.aiStopped,
                      style: text.caption.copyWith(color: colors.textMuted),
                    ),
                  if (turn.failed) ...[
                    Row(
                      children: [
                        Icon(
                          Icons.error_outline_rounded,
                          color: colors.negativeText,
                          size: 20,
                        ),
                        const SizedBox(width: AppSpacing.xs),
                        Expanded(
                          child: Text(
                            turn.error!,
                            style: text.body.copyWith(
                              color: colors.negativeText,
                            ),
                          ),
                        ),
                      ],
                    ),
                    if (onRetry != null)
                      Align(
                        alignment: AlignmentDirectional.centerEnd,
                        child: TextButton(
                          onPressed: onRetry,
                          child: Text(l10n.retry),
                        ),
                      ),
                  ],
                ],
              ),
            ),
        ],
      ),
    );
  }
}

class _Progress extends StatelessWidget {
  const _Progress({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsetsDirectional.only(bottom: AppSpacing.s),
    child: Row(
      children: [
        const SizedBox(
          width: 16,
          height: 16,
          child: CircularProgressIndicator(strokeWidth: 2),
        ),
        const SizedBox(width: AppSpacing.xs),
        Expanded(child: Text(text, style: context.wealthText.caption)),
      ],
    ),
  );
}

/// A refusal looks different from an answer, so it is never mistaken for one.
class _RefusalCard extends StatelessWidget {
  const _RefusalCard({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final colors = context.wealthColors;
    return Semantics(
      container: true,
      child: DecoratedBox(
        key: const ValueKey('refusal'),
        decoration: BoxDecoration(
          color: colors.staleBanner,
          borderRadius: AppRadii.mediumRadius,
          border: Border.all(color: colors.warning),
        ),
        child: Padding(
          padding: const EdgeInsetsDirectional.all(AppSpacing.m),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(Icons.block_rounded, color: colors.onStaleBanner),
              const SizedBox(width: AppSpacing.s),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      l10n.aiRefusalTitle,
                      style: context.wealthText.title.copyWith(
                        color: colors.onStaleBanner,
                      ),
                    ),
                    const SizedBox(height: AppSpacing.xxs),
                    Text(
                      text,
                      style: context.wealthText.body.copyWith(
                        color: colors.onStaleBanner,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Footer extends StatelessWidget {
  const _Footer({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsetsDirectional.fromSTEB(
      AppSpacing.m,
      0,
      AppSpacing.m,
      AppSpacing.xs,
    ),
    child: Text(
      text,
      style: context.wealthText.caption.copyWith(
        color: context.wealthColors.textMuted,
      ),
      textAlign: TextAlign.center,
    ),
  );
}
