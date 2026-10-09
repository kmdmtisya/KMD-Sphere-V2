import 'package:flutter/widgets.dart';

import '../formatting/formatting.dart';

extension LocaleFormatting on BuildContext {
  /// The active locale in the form the formatters expect (`en`, `de_DE`, ...).
  String get formatLocale => Localizations.localeOf(this).toString();

  MoneyFormatter get moneyFormatter => MoneyFormatter(locale: formatLocale);

  PercentFormatter get percentFormatter =>
      PercentFormatter(locale: formatLocale);
}
