import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../l10n/generated/app_localizations.dart';

/// The app's strings outside the widget tree, for repositories that label server data (P12-T09):
/// the device's language when the app supports it, English otherwise.
final l10nProvider = Provider<AppLocalizations>((ref) {
  final device = WidgetsBinding.instance.platformDispatcher.locale;
  const supported = AppLocalizations.supportedLocales;
  final match = supported.firstWhere(
    (l) => l.languageCode == device.languageCode,
    orElse: () => supported.first,
  );
  return lookupAppLocalizations(match);
});
