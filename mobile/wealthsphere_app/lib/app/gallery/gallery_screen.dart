import 'package:flutter/material.dart';

import '../../shared/design_system/components/components.dart';
import '../../shared/design_system/theme/theme.dart';
import '../../shared/design_system/tokens/tokens.dart';
import 'gallery_sections.dart';

/// Debug-only catalogue of every design-system component, with toggles for theme, text size and
/// right-to-left layout, so the visual language can be reviewed in every condition at once.
/// The route is registered only in debug builds (see `createRouter`).
class GalleryScreen extends StatefulWidget {
  const GalleryScreen({super.key});

  @override
  State<GalleryScreen> createState() => _GalleryScreenState();
}

class _GalleryScreenState extends State<GalleryScreen> {
  Brightness? _brightness;
  double _scale = 1.0;
  bool _rtl = false;

  @override
  Widget build(BuildContext context) {
    final brightness = _brightness ?? Theme.of(context).brightness;
    final theme = brightness == Brightness.dark
        ? AppTheme.dark()
        : AppTheme.light();

    return Theme(
      data: theme,
      child: Directionality(
        textDirection: _rtl ? TextDirection.rtl : TextDirection.ltr,
        child: MediaQuery(
          data: MediaQuery.of(context)
              .copyWith(textScaler: TextScaler.linear(_scale)),
          child: Scaffold(
            appBar: AppBar(
              title: const Text('Component gallery'),
              actions: const [
                DemoBadge(),
                SizedBox(width: AppSpacing.m),
              ],
            ),
            body: ListView(
              padding: const EdgeInsetsDirectional.all(AppSpacing.m),
              children: [
                _Controls(
                  brightness: brightness,
                  scale: _scale,
                  rtl: _rtl,
                  onBrightness: (b) => setState(() => _brightness = b),
                  onScale: (s) => setState(() => _scale = s),
                  onRtl: (v) => setState(() => _rtl = v),
                ),
                for (final section in gallerySections) ...[
                  const SizedBox(height: AppSpacing.l),
                  Text(section.title, style: theme.textTheme.titleMedium),
                  const SizedBox(height: AppSpacing.s),
                  section.builder(context, animated: true),
                ],
                const SizedBox(height: AppSpacing.xl),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _Controls extends StatelessWidget {
  const _Controls({
    required this.brightness,
    required this.scale,
    required this.rtl,
    required this.onBrightness,
    required this.onScale,
    required this.onRtl,
  });

  final Brightness brightness;
  final double scale;
  final bool rtl;
  final ValueChanged<Brightness> onBrightness;
  final ValueChanged<double> onScale;
  final ValueChanged<bool> onRtl;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: AppSpacing.m,
      runSpacing: AppSpacing.s,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        SegmentedButton<Brightness>(
          showSelectedIcon: false,
          segments: const [
            ButtonSegment(value: Brightness.light, label: Text('Light')),
            ButtonSegment(value: Brightness.dark, label: Text('Dark')),
          ],
          selected: {brightness},
          onSelectionChanged: (s) => onBrightness(s.first),
        ),
        SegmentedButton<double>(
          showSelectedIcon: false,
          segments: const [
            ButtonSegment(value: 1.0, label: Text('1.0x')),
            ButtonSegment(value: 1.5, label: Text('1.5x')),
            ButtonSegment(value: 2.0, label: Text('2.0x')),
          ],
          selected: {scale},
          onSelectionChanged: (s) => onScale(s.first),
        ),
        Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Switch(value: rtl, onChanged: onRtl),
            const SizedBox(width: AppSpacing.xs),
            const Text('RTL'),
          ],
        ),
      ],
    );
  }
}
