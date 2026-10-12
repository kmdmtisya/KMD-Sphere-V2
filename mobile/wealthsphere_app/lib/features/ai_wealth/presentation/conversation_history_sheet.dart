import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../app/app_routes.dart';
import '../../../l10n/generated/app_localizations.dart';
import '../../../shared/design_system/components/components.dart';
import '../../../shared/design_system/theme/theme.dart';
import '../../../shared/design_system/tokens/tokens.dart';
import '../../copilot/data/copilot_repository.dart';
import '../../copilot/domain/conversation_models.dart';
import '../application/copilot_controller.dart';

final _historyProvider = FutureProvider.autoDispose<List<ConversationSummary>>(
  (ref) => ref.watch(copilotRepositoryProvider).conversations(),
);

/// The user's stored conversations: open one to continue it, delete one or all of them. Shows
/// its own loading, error and empty states.
class ConversationHistorySheet extends ConsumerWidget {
  const ConversationHistorySheet({super.key});

  Future<void> _open(
    BuildContext context,
    WidgetRef ref,
    ConversationSummary summary,
  ) async {
    final l10n = AppLocalizations.of(context);
    final messenger = ScaffoldMessenger.of(context);
    final navigator = Navigator.of(context);
    final controller = ref.read(copilotControllerProvider.notifier);
    try {
      final detail = await ref
          .read(copilotRepositoryProvider)
          .conversation(summary.id);
      controller.open(
        conversationId: summary.id,
        turns: detail.toTurns(),
        scope: summary.portfolioId == null
            ? null
            : AiScope(AiScopeKind.portfolio, summary.portfolioId!),
      );
      navigator.pop();
    } on Object {
      messenger.showSnackBar(SnackBar(content: Text(l10n.aiHistoryOpenFailed)));
    }
  }

  Future<void> _delete(
    BuildContext context,
    WidgetRef ref,
    ConversationSummary summary,
  ) async {
    final l10n = AppLocalizations.of(context);
    final messenger = ScaffoldMessenger.of(context);
    try {
      await ref.read(copilotRepositoryProvider).deleteConversation(summary.id);
      ref.read(copilotControllerProvider.notifier).forget(summary.id);
      ref.invalidate(_historyProvider);
    } on Object {
      messenger.showSnackBar(
        SnackBar(content: Text(l10n.aiHistoryDeleteFailed)),
      );
    }
  }

  Future<void> _deleteAll(BuildContext context, WidgetRef ref) async {
    final l10n = AppLocalizations.of(context);
    final messenger = ScaffoldMessenger.of(context);
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(l10n.aiHistoryDeleteAllTitle),
        content: Text(l10n.aiHistoryDeleteAllBody),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: Text(l10n.ledgerCancel),
          ),
          TextButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: Text(l10n.aiHistoryDeleteAll),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    try {
      await ref.read(copilotRepositoryProvider).deleteAllConversations();
      ref.read(copilotControllerProvider.notifier).clear();
      ref.invalidate(_historyProvider);
    } on Object {
      messenger.showSnackBar(
        SnackBar(content: Text(l10n.aiHistoryDeleteFailed)),
      );
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    final text = context.wealthText;
    final history = ref.watch(_historyProvider);
    return SafeArea(
      child: ConstrainedBox(
        constraints: BoxConstraints(
          maxHeight: MediaQuery.sizeOf(context).height * 0.8,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsetsDirectional.symmetric(
                horizontal: AppSpacing.m,
              ),
              child: Row(
                children: [
                  Expanded(
                    child: Semantics(
                      header: true,
                      child: Text(l10n.aiHistoryTitle, style: text.title),
                    ),
                  ),
                  if (history.value?.isNotEmpty ?? false)
                    TextButton(
                      onPressed: () => _deleteAll(context, ref),
                      child: Text(l10n.aiHistoryDeleteAll),
                    ),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsetsDirectional.symmetric(
                horizontal: AppSpacing.m,
                vertical: AppSpacing.xs,
              ),
              child: Text(l10n.aiHistoryRetention, style: text.caption),
            ),
            Flexible(
              child: AsyncValueView<List<ConversationSummary>>(
                value: history,
                onRetry: () => ref.invalidate(_historyProvider),
                isEmpty: (items) => items.isEmpty,
                empty: EmptyState(
                  icon: Icons.chat_bubble_outline_rounded,
                  message: l10n.aiHistoryEmpty,
                ),
                data: (items) => ListView(
                  shrinkWrap: true,
                  children: [
                    for (final c in items)
                      ListTile(
                        key: ValueKey('conversation-${c.id}'),
                        title: Text(
                          c.title ?? l10n.aiHistoryUntitled,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                        ),
                        subtitle: Text(
                          MaterialLocalizations.of(context)
                              .formatMediumDate(c.updatedAt.toLocal()),
                        ),
                        onTap: () => _open(context, ref, c),
                        trailing: IconButton(
                          tooltip: l10n.aiHistoryDelete,
                          icon: const Icon(Icons.delete_outline_rounded),
                          onPressed: () => _delete(context, ref, c),
                        ),
                      ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
