import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../app/app_routes.dart';
import '../../../core/preferences/preferences_store.dart';
import '../../../l10n/generated/app_localizations.dart';
import '../../../shared/design_system/theme/wealth_typography.dart';
import '../../../shared/design_system/tokens/tokens.dart';
import '../application/auth_flow.dart';

/// Screen 1: brand intro and a three-slide introduction. Skip is always available (and labelled
/// for screen readers); every slide can also be reached with Next, so swiping is never required.
class WelcomeScreen extends ConsumerStatefulWidget {
  const WelcomeScreen({super.key});

  @override
  ConsumerState<WelcomeScreen> createState() => _WelcomeScreenState();
}

class _Slide {
  const _Slide(this.icon, this.title, this.body);

  final IconData icon;
  final String Function(AppLocalizations) title;
  final String Function(AppLocalizations) body;
}

final _slides = [
  _Slide(
    Icons.account_balance_wallet_outlined,
    (l) => l.welcomeSlide1Title,
    (l) => l.welcomeSlide1Body,
  ),
  _Slide(
    Icons.insights_outlined,
    (l) => l.welcomeSlide2Title,
    (l) => l.welcomeSlide2Body,
  ),
  _Slide(
    Icons.auto_awesome_outlined,
    (l) => l.welcomeSlide3Title,
    (l) => l.welcomeSlide3Body,
  ),
];

class _WelcomeScreenState extends ConsumerState<WelcomeScreen> {
  final _pages = PageController();
  int _page = 0;

  @override
  void dispose() {
    _pages.dispose();
    super.dispose();
  }

  Future<void> _finish() async {
    await markOnboardingComplete(ref.read(preferencesStoreProvider));
    if (mounted) context.go(AppRoutes.signIn);
  }

  void _next() {
    if (_page >= _slides.length - 1) {
      _finish();
      return;
    }
    final target = _page + 1;
    if (MediaQuery.disableAnimationsOf(context)) {
      _pages.jumpToPage(target);
    } else {
      _pages.animateToPage(
        target,
        duration: const Duration(milliseconds: 250),
        curve: Curves.easeOut,
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final colors = context.wealthColors;
    final last = _page == _slides.length - 1;
    return Scaffold(
      backgroundColor: colors.scaffold,
      body: SafeArea(
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: AppSpacing.m),
              child: Row(
                children: [
                  Icon(Icons.public, color: colors.primary),
                  const SizedBox(width: AppSpacing.xs),
                  Expanded(
                    child: Text(
                      l10n.appTitle,
                      style: context.wealthText.title,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  if (!last)
                    TextButton(
                      key: const ValueKey('welcome-skip'),
                      onPressed: _finish,
                      child: Text(
                        l10n.welcomeSkip,
                        semanticsLabel: l10n.welcomeSkipLabel,
                      ),
                    ),
                ],
              ),
            ),
            Expanded(
              child: PageView.builder(
                controller: _pages,
                itemCount: _slides.length,
                onPageChanged: (i) => setState(() => _page = i),
                itemBuilder: (context, i) => _SlideView(
                  key: ValueKey('welcome-slide-$i'),
                  slide: _slides[i],
                  position: l10n.welcomeSlideLabel(i + 1, _slides.length),
                ),
              ),
            ),
            _Dots(count: _slides.length, current: _page),
            Padding(
              padding: const EdgeInsets.all(AppSpacing.m),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  FilledButton(
                    key: const ValueKey('welcome-next'),
                    onPressed: _next,
                    child: Text(
                      last ? l10n.welcomeGetStarted : l10n.welcomeNext,
                    ),
                  ),
                  const SizedBox(height: AppSpacing.xs),
                  TextButton(
                    key: const ValueKey('welcome-sign-in'),
                    onPressed: _finish,
                    child: Text(l10n.welcomeHaveAccount),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SlideView extends StatelessWidget {
  const _SlideView({required this.slide, required this.position, super.key});

  final _Slide slide;
  final String position;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final colors = context.wealthColors;
    return Semantics(
      container: true,
      hint: position,
      child: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.l),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 480),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                ExcludeSemantics(
                  child: Icon(slide.icon, size: 72, color: colors.primary),
                ),
                const SizedBox(height: AppSpacing.l),
                Semantics(
                  header: true,
                  child: Text(
                    slide.title(l10n),
                    style: context.wealthText.headline,
                    textAlign: TextAlign.center,
                  ),
                ),
                const SizedBox(height: AppSpacing.s),
                Text(
                  slide.body(l10n),
                  style: context.wealthText.body,
                  textAlign: TextAlign.center,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// Position dots. Decorative for screen readers (each slide announces "Slide n of 3").
class _Dots extends StatelessWidget {
  const _Dots({required this.count, required this.current});

  final int count;
  final int current;

  @override
  Widget build(BuildContext context) {
    final colors = context.wealthColors;
    return ExcludeSemantics(
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          for (var i = 0; i < count; i++)
            AnimatedContainer(
              duration: const Duration(milliseconds: 200),
              margin: const EdgeInsets.symmetric(horizontal: 4),
              width: i == current ? 20 : 8,
              height: 8,
              decoration: BoxDecoration(
                color: i == current ? colors.primary : colors.border,
                borderRadius: BorderRadius.circular(4),
              ),
            ),
        ],
      ),
    );
  }
}
