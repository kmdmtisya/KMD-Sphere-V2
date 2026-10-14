import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../../../core/data/data_source_badge.dart';
import '../../../l10n/generated/app_localizations.dart';
import '../../../shared/design_system/theme/theme.dart';
import '../../../shared/design_system/tokens/tokens.dart';

/// The More tab: where the wealth views, tools and settings live. Entries that are not built yet
/// are listed as "Coming soon" and cannot be opened, so nothing leads to a dead end.
class MoreScreen extends StatelessWidget {
  const MoreScreen({
    this.onOpenNetWorth,
    this.onOpenIncome,
    this.onOpenCalculator,
    this.onOpenSettings,
    this.onOpenAlerts,
    this.onOpenConverter,
    this.onOpenForex,
    this.onOpenGallery,
    super.key,
  });

  final VoidCallback? onOpenNetWorth;
  final VoidCallback? onOpenIncome;
  final VoidCallback? onOpenCalculator;
  final VoidCallback? onOpenSettings;
  final VoidCallback? onOpenAlerts;
  final VoidCallback? onOpenConverter;

  /// Set only when the forex section is available (DEMO, or switched on on the server).
  final VoidCallback? onOpenForex;

  /// Debug builds only.
  final VoidCallback? onOpenGallery;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.tabMore),
        actions: const [
          DataSourceBadge(),
          SizedBox(width: AppSpacing.m),
        ],
      ),
      body: ListView(
        padding: const EdgeInsetsDirectional.symmetric(vertical: AppSpacing.s),
        children: [
          _Heading(l10n.moreSectionWealth),
          _MoreTile(
            icon: Icons.account_balance_wallet_outlined,
            title: l10n.moreNetWorth,
            subtitle: l10n.moreNetWorthSub,
            onTap: onOpenNetWorth,
          ),
          _MoreTile(
            icon: Icons.payments_outlined,
            title: l10n.moreIncome,
            subtitle: l10n.moreIncomeSub,
            onTap: onOpenIncome,
          ),
          _MoreTile(
            icon: Icons.calculate_outlined,
            title: l10n.moreCalculator,
            subtitle: l10n.moreCalculatorSub,
            onTap: onOpenCalculator,
          ),
          _MoreTile(
            icon: Icons.currency_exchange_rounded,
            title: l10n.converterTitle,
            subtitle: l10n.converterSub,
            onTap: onOpenConverter,
          ),
          _MoreTile(
            icon: Icons.notifications_none_rounded,
            title: l10n.watchlistAlertsTitle,
            subtitle: l10n.moreWatchlistAlertsSub,
            onTap: onOpenAlerts,
          ),
          if (onOpenForex != null)
            _MoreTile(
              icon: Icons.candlestick_chart_outlined,
              title: l10n.fxTitle,
              subtitle: l10n.fxEntrySubtitle,
              onTap: onOpenForex,
            ),
          _Heading(l10n.moreSectionSoon),
          _MoreTile(
            icon: Icons.description_outlined,
            title: l10n.moreReports,
            comingSoon: true,
          ),
          _MoreTile(
            icon: Icons.folder_open_rounded,
            title: l10n.moreDocuments,
            comingSoon: true,
          ),
          _Heading(l10n.moreSectionApp),
          _MoreTile(
            icon: Icons.settings_outlined,
            title: l10n.moreSettings,
            subtitle: l10n.moreSettingsSub,
            onTap: onOpenSettings,
          ),
          if (kDebugMode && onOpenGallery != null)
            _MoreTile(
              icon: Icons.palette_outlined,
              title: 'Component gallery (debug)',
              onTap: onOpenGallery,
            ),
        ],
      ),
    );
  }
}

class _Heading extends StatelessWidget {
  const _Heading(this.text);

  final String text;

  @override
  Widget build(BuildContext context) => Semantics(
    header: true,
    child: Padding(
      padding: const EdgeInsetsDirectional.fromSTEB(
        AppSpacing.m,
        AppSpacing.m,
        AppSpacing.m,
        AppSpacing.xxs,
      ),
      child: Text(
        text,
        style: context.wealthText.label.copyWith(
          color: context.wealthColors.textMuted,
        ),
      ),
    ),
  );
}

/// One entry. A "coming soon" entry is visibly and audibly unavailable.
class _MoreTile extends StatelessWidget {
  const _MoreTile({
    required this.icon,
    required this.title,
    this.subtitle,
    this.onTap,
    this.comingSoon = false,
  });

  final IconData icon;
  final String title;
  final String? subtitle;
  final VoidCallback? onTap;
  final bool comingSoon;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final text = context.wealthText;
    final colors = context.wealthColors;
    final muted = text.caption.copyWith(color: colors.textMuted);
    final enabled = !comingSoon && onTap != null;
    final tile = ConstrainedBox(
      constraints: const BoxConstraints(minHeight: AppTouchTarget.android),
      child: Padding(
        padding: const EdgeInsetsDirectional.symmetric(
          horizontal: AppSpacing.m,
          vertical: AppSpacing.s,
        ),
        child: Row(
          children: [
            Icon(icon, color: enabled ? colors.textPrimary : colors.textMuted),
            const SizedBox(width: AppSpacing.m),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: text.title.copyWith(
                      color: enabled ? null : colors.textMuted,
                    ),
                  ),
                  // "Coming soon" sits under the title so it never competes for width with it.
                  if (comingSoon)
                    Text(l10n.moreComingSoon, style: muted)
                  else if (subtitle != null)
                    Text(subtitle!, style: muted),
                ],
              ),
            ),
            if (!comingSoon)
              Icon(
                Directionality.of(context) == TextDirection.rtl
                    ? Icons.chevron_left_rounded
                    : Icons.chevron_right_rounded,
                color: colors.textMuted,
              ),
          ],
        ),
      ),
    );

    if (comingSoon) {
      return Semantics(
        container: true,
        label: l10n.moreComingSoonSpoken(title),
        excludeSemantics: true,
        child: tile,
      );
    }
    return Semantics(
      container: true,
      button: true,
      label: [title, ?subtitle].join(', '),
      excludeSemantics: true,
      onTap: onTap,
      child: InkWell(onTap: onTap, child: tile),
    );
  }
}
