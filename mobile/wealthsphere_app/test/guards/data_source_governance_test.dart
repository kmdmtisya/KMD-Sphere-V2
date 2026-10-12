@Tags(['security'])
library;

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/core/config/app_config.dart';
import 'package:wealthsphere_app/core/data/data_source_badge.dart';
import 'package:wealthsphere_app/core/data/demo_support.dart';

import '../helpers/demo_overrides.dart';
import '../helpers/pump_app.dart';

const _base = AppConfig(
  apiBaseUrl: 'https://api.example',
  oidcIssuer: 'https://id.example',
);

AppConfig config(String source) => AppConfig(
  apiBaseUrl: _base.apiBaseUrl,
  oidcIssuer: _base.oidcIssuer,
  dataSource: source,
);

ProviderContainer container(String source, {required bool release}) =>
    ProviderContainer(
      overrides: [
        appConfigProvider.overrideWithValue(config(source)),
        releaseBuildProvider.overrideWithValue(release),
      ],
    );

/// Screens whose data is always demo until the AI services exist (P10): they may show the DEMO
/// badge unconditionally. Everything else must use `DataSourceBadge`.
const _alwaysDemo = {
  'lib/features/ai_wealth/doctor/presentation/doctor_screen.dart',
  'lib/features/ai_wealth/opportunities/presentation/compare_screen.dart',
  'lib/features/ai_wealth/opportunities/presentation/opportunities_screen.dart',
  'lib/features/ai_wealth/presentation/ai_wealth_screen.dart',
  // The badge itself, the card that labels a demo opportunity, the developer gallery and the
  // placeholder screens.
  'lib/shared/design_system/components/demo_badge.dart',
  'lib/shared/design_system/components/opportunity_card.dart',
  'lib/core/data/data_source_badge.dart',
  'lib/app/gallery/gallery_screen.dart',
  'lib/app/gallery/gallery_sections.dart',
  'lib/app/placeholder_screens.dart',
};

void main() {
  group('release builds refuse DEMO data', () {
    test('asking for demo in a release build fails at start', () {
      expect(
        () => container('demo', release: true).read(dataSourceModeProvider),
        throwsA(anything),
      );
    });

    test('live is accepted in a release build', () {
      expect(
        container('live', release: true).read(dataSourceModeProvider),
        DataSourceMode.live,
      );
    });

    test('demo is fine in a debug build or a test', () {
      expect(
        container('demo', release: false).read(dataSourceModeProvider),
        DataSourceMode.demo,
      );
    });

    test(
      'the mode cannot be switched to demo at run time in a release build',
      () {
        final c = container('live', release: true);
        addTearDown(c.dispose);
        final notifier = c.read(dataSourceModeProvider.notifier);
        expect(
          () => notifier.set(DataSourceMode.demo),
          throwsA(isA<StateError>()),
        );
        expect(c.read(dataSourceModeProvider), DataSourceMode.live);
      },
    );

    test('the configuration itself rejects demo for a release build', () {
      expect(
        () => config('demo').assertDataSourceFor(release: true),
        throwsStateError,
      );
      expect(
        () => config('live').assertDataSourceFor(release: true),
        returnsNormally,
      );
      expect(
        () => config('demo').assertDataSourceFor(release: false),
        returnsNormally,
      );
    });

    test('policy function', () {
      expect(
        () => enforceDataSourcePolicy(DataSourceMode.demo, release: true),
        throwsStateError,
      );
      expect(
        enforceDataSourcePolicy(DataSourceMode.live, release: true),
        DataSourceMode.live,
      );
    });
  });

  group('DEMO labelling follows the actual data source', () {
    testWidgets('shown on demo data', (tester) async {
      await tester.pumpApp(const Scaffold(body: DataSourceBadge()));
      expect(find.text('DEMO'), findsOneWidget);
    });

    testWidgets('absent on live data', (tester) async {
      await tester.pumpApp(
        const Scaffold(body: DataSourceBadge()),
        overrides: demoOverrides(extra: [liveModeOverride()]),
      );
      expect(find.text('DEMO'), findsNothing);
    });
  });

  group('source guards', () {
    final lib = Directory('lib');
    final files = [
      for (final f in lib.listSync(recursive: true))
        if (f is File && f.path.endsWith('.dart')) f,
    ];
    String rel(File f) => f.path.replaceAll(r'\', '/');

    test('only always-demo screens show the DEMO badge unconditionally', () {
      final offenders = [
        for (final f in files)
          if (!_alwaysDemo.contains(rel(f)) &&
              RegExp(r'\bDemo(Badge|Banner)\(').hasMatch(f.readAsStringSync()))
            rel(f),
      ];
      expect(
        offenders,
        isEmpty,
        reason:
            'use DataSourceBadge, so DEMO is shown only while the data is demo',
      );
    });

    test('no repository provider is left unwired in live mode', () {
      final offenders = [
        for (final f in files)
          if (f.readAsStringSync().contains('liveNotWired(')) rel(f),
      ];
      expect(offenders, isEmpty);
    });

    test('every data repository provider has a live branch', () {
      // A provider that switches on the mode must handle both cases (a missing case would not
      // compile, so this guards against `default:` hiding one).
      final offenders = [
        for (final f in files)
          if (RegExp(r'switch \(ref\.watch\(dataSourceModeProvider\)\)')
                  .hasMatch(f.readAsStringSync()) &&
              !f.readAsStringSync().contains('DataSourceMode.live'))
            rel(f),
      ];
      expect(offenders, isEmpty);
    });

    test('demo fixtures are loaded only through the demo support', () {
      bool codeMentions(File f) => f.readAsLinesSync().any(
        (l) => !l.trimLeft().startsWith('//') && l.contains('assets/demo/'),
      );
      final offenders = [
        for (final f in files)
          if (rel(f) != 'lib/core/data/demo_support.dart' && codeMentions(f))
            rel(f),
      ];
      expect(offenders, isEmpty);
    });
  });
}
