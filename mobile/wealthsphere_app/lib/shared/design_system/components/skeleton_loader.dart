import 'package:flutter/material.dart';

import '../../../l10n/generated/app_localizations.dart';
import '../tokens/tokens.dart';

/// A placeholder block. Compose several inside a [SkeletonLoader]; on its own it is a plain,
/// static, rounded rectangle.
class SkeletonBox extends StatelessWidget {
  const SkeletonBox({
    this.width,
    this.height = 16,
    this.radius = AppRadii.small,
    super.key,
  });

  final double? width;
  final double height;
  final double radius;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: context.wealthColors.divider,
        borderRadius: BorderRadius.circular(radius),
      ),
      child: SizedBox(width: width, height: height),
    );
  }
}

/// Shimmering loading placeholder for content that is on its way.
///
/// One shimmer animates over the whole [child] (not one per box). The shimmer stops entirely when
/// the platform requests reduced motion or [animate] is false. Screen readers hear a single
/// "Loading" announcement instead of the individual blocks.
class SkeletonLoader extends StatefulWidget {
  const SkeletonLoader({required this.child, this.animate = true, super.key});

  /// A card-shaped placeholder: a title bar and two text lines.
  factory SkeletonLoader.card({bool animate = true, Key? key}) =>
      SkeletonLoader(
        key: key,
        animate: animate,
        child: const Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            SkeletonBox(width: 140, height: 20),
            SizedBox(height: AppSpacing.s),
            SkeletonBox(height: 14),
            SizedBox(height: AppSpacing.xs),
            SkeletonBox(width: 220, height: 14),
          ],
        ),
      );

  /// [count] text lines of decreasing width.
  factory SkeletonLoader.lines({
    int count = 3,
    bool animate = true,
    Key? key,
  }) => SkeletonLoader(
    key: key,
    animate: animate,
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        for (var i = 0; i < count; i++) ...[
          if (i > 0) const SizedBox(height: AppSpacing.xs),
          SkeletonBox(width: i == count - 1 ? 160 : null, height: 14),
        ],
      ],
    ),
  );

  final Widget child;
  final bool animate;

  @override
  State<SkeletonLoader> createState() => _SkeletonLoaderState();
}

class _SkeletonLoaderState extends State<SkeletonLoader>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 1400),
  );

  bool _running = false;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _sync(bool shouldRun) {
    if (shouldRun == _running) return;
    _running = shouldRun;
    if (shouldRun) {
      _controller.repeat();
    } else {
      _controller.stop();
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final colors = context.wealthColors;
    final reduceMotion = MediaQuery.disableAnimationsOf(context);
    _sync(widget.animate && !reduceMotion);

    final base = colors.divider;
    final highlight = Color.alphaBlend(
      colors.textPrimary.withValues(alpha: 0.10),
      base,
    );
    final direction = Directionality.of(context);

    final content = ExcludeSemantics(child: widget.child);
    final shimmering = _running
        ? AnimatedBuilder(
            animation: _controller,
            child: content,
            builder: (context, child) => ShaderMask(
              blendMode: BlendMode.srcATop,
              shaderCallback: (bounds) => LinearGradient(
                colors: [base, highlight, base],
                stops: const [0.2, 0.5, 0.8],
                begin: AlignmentDirectional(-1.5 + 3 * _controller.value, 0),
                end: AlignmentDirectional(-0.5 + 3 * _controller.value, 0),
              ).createShader(bounds, textDirection: direction),
              child: child,
            ),
          )
        : content;

    return Semantics(label: l10n.loading, liveRegion: true, child: shimmering);
  }
}
