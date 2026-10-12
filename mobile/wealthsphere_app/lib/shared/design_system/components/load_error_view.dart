import 'package:flutter/material.dart';

import '../../../core/network/load_failure.dart';
import '../../../l10n/generated/app_localizations.dart';
import 'state_views.dart';

/// The error state for a failed load, worded for the cause: offline, session ended, refused,
/// missing, busy or generic. Shows the API support reference when there is one, never the
/// exception text. Retry appears only when retrying can help.
class LoadErrorView extends StatelessWidget {
  const LoadErrorView({required this.error, this.onRetry, super.key});

  final Object? error;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final failure = loadFailureOf(error);
    final reference = supportReferenceOf(error);
    final (title, message) = switch (failure) {
      LoadFailure.offline => (l10n.errorOfflineTitle, l10n.errorOfflineMessage),
      LoadFailure.signedOut => (
        l10n.errorSessionEndedTitle,
        l10n.errorSessionEndedMessage,
      ),
      LoadFailure.forbidden => (
        l10n.errorForbiddenTitle,
        l10n.errorForbiddenMessage,
      ),
      LoadFailure.notFound => (
        l10n.errorNotFoundTitle,
        l10n.errorNotFoundMessage,
      ),
      LoadFailure.busy => (l10n.errorGenericTitle, l10n.errorBusyMessage),
      LoadFailure.unknown => (l10n.errorGenericTitle, l10n.errorGenericMessage),
    };
    return ErrorState(
      title: title,
      message: reference == null
          ? message
          : '$message\n${l10n.errorSupportReference(reference)}',
      onRetry: failure.retryable ? onRetry : null,
    );
  }
}
