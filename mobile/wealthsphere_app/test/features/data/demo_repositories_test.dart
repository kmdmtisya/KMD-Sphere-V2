import 'dart:convert';
import 'dart:io';

import 'package:decimal/decimal.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/app/app_routes.dart';
import 'package:wealthsphere_app/core/data/demo_support.dart';
import 'package:wealthsphere_app/core/data/json_reader.dart';
import 'package:wealthsphere_app/core/preferences/preferences_store.dart';
import 'package:wealthsphere_app/features/copilot/data/copilot_repository.dart';
import 'package:wealthsphere_app/features/copilot/domain/chat_models.dart';
import 'package:wealthsphere_app/features/dashboard/data/dashboard_repository.dart';
import 'package:wealthsphere_app/features/dashboard/domain/dashboard_layout.dart';
import 'package:wealthsphere_app/features/forecast/data/forecast_repository.dart';
import 'package:wealthsphere_app/features/forecast/domain/forecast_models.dart';
import 'package:wealthsphere_app/features/portfolios/data/portfolio_repository.dart';
import 'package:wealthsphere_app/shared/design_system/components/period_selector.dart';
import 'package:wealthsphere_app/shared/domain/wealth_models.dart';

import '../../helpers/demo_container.dart';

const ids = ['p-retire', 'p-growth', 'p-income', PortfolioRef.consolidatedId];

void main() {
  test('every fixture file is marked demo', () {
    final files = Directory('assets/demo')
        .listSync()
        .whereType<File>()
        .where((f) => f.path.endsWith('.json'));
    expect(files, isNotEmpty);
    for (final f in files) {
      final json = jsonDecode(f.readAsStringSync()) as Map<String, dynamic>;
      expect(json['demo'], true, reason: f.path);
    }
  });

  group('PortfolioRepository (demo)', () {
    test('three portfolios plus the consolidated view', () async {
      final repo = demoContainer().read(portfolioRepositoryProvider);
      final list = await repo.portfolios();
      expect(list.map((p) => p.id), ['p-retire', 'p-growth', 'p-income']);
      expect(
        (await repo.summary(PortfolioRef.consolidatedId)).name,
        'All portfolios',
      );
    });

    test('summaries are internally consistent (exact decimals)', () async {
      final repo = demoContainer().read(portfolioRepositoryProvider);
      for (final id in ids) {
        final s = await repo.summary(id);
        expect(
          s.value.amount - s.invested.amount,
          s.profitLoss.amount,
          reason: id,
        );
        expect(s.value.currencyCode, 'USD');
      }
      final parts = [for (final id in ids.take(3)) await repo.summary(id)];
      final all = await repo.summary(PortfolioRef.consolidatedId);
      expect(
        parts.fold<Decimal>(Decimal.zero, (a, s) => a + s.value.amount),
        all.value.amount,
      );
    });

    test(
      'holdings add up to the portfolio value and include AED and KES natives',
      () async {
        final repo = demoContainer().read(portfolioRepositoryProvider);
        for (final id in ids) {
          final holdings = await repo.holdings(id);
          final total = holdings.fold<Decimal>(
            Decimal.zero,
            (a, h) => a + h.value.amount,
          );
          expect(total, (await repo.summary(id)).value.amount, reason: id);
        }
        final natives = {
          for (final h in await repo.holdings(PortfolioRef.consolidatedId))
            h.nativeValue.currencyCode,
        };
        expect(natives, containsAll(['USD', 'AED', 'KES']));
      },
    );

    test('allocation weights are server-supplied and sum to 100', () async {
      final repo = demoContainer().read(portfolioRepositoryProvider);
      for (final id in ids) {
        final slices = await repo.allocation(id);
        expect(slices, isNotEmpty);
        expect(
          slices.fold<Decimal>(Decimal.zero, (a, s) => a + s.weightPercent),
          Decimal.fromInt(100),
          reason: id,
        );
      }
    });

    test(
      'a series exists for every period and ends at the current value',
      () async {
        final repo = demoContainer().read(portfolioRepositoryProvider);
        for (final id in ids) {
          final value = (await repo.summary(id)).value.amount;
          for (final period in ChartPeriod.values) {
            final series = await repo.performance(id, period);
            expect(
              series.points.length,
              greaterThanOrEqualTo(2),
              reason: '$id $period',
            );
            for (var i = 1; i < series.points.length; i++) {
              expect(
                series.points[i].date.isBefore(series.points[i - 1].date),
                isFalse,
                reason: '$id $period order',
              );
            }
            expect(series.points.last.value, value, reason: '$id $period end');
            expect(series.currencyCode, 'USD');
          }
        }
      },
    );

    test('metrics exist for every portfolio', () async {
      final repo = demoContainer().read(portfolioRepositoryProvider);
      for (final id in ids) {
        final m = await repo.metrics(id);
        expect(m.volatilityPercent, greaterThan(Decimal.zero));
      }
    });

    test('an unknown portfolio is an error, not empty data', () async {
      final repo = demoContainer().read(portfolioRepositoryProvider);
      await expectLater(
        repo.summary('nope'),
        throwsA(isA<DataLoadException>()),
      );
      await expectLater(
        repo.holdings('nope'),
        throwsA(isA<DataLoadException>()),
      );
    });

    test('summary JSON round-trips without losing decimal precision', () async {
      final s = await demoContainer()
          .read(portfolioRepositoryProvider)
          .summary('p-growth');
      final again = PortfolioSummary.fromJson(JsonReader(s.toJson()));
      expect(again.value, s.value);
      expect(again.returnPercent, s.returnPercent);
      expect(again.asOf, s.asOf);
    });
  });

  group('DashboardRepository (demo)', () {
    test('every section loads', () async {
      final repo = demoContainer().read(dashboardRepositoryProvider);
      expect(await repo.greetingName(), isNotEmpty);
      final nw = await repo.netWorth();
      expect(nw.assets.amount - nw.liabilities.amount, nw.netWorth.amount);
      final income = await repo.income();
      expect(income.monthly.amount * Decimal.fromInt(12), income.yearly.amount);
      final goals = await repo.goals();
      expect(goals.items.length, goals.total);
      expect(
        goals.items.where((g) => g.status == GoalStatus.onTrack).length,
        goals.onTrack,
      );
      final insight = await repo.insight();
      expect(insight.sources, isNotEmpty);
    });
  });

  group('ForecastRepository (demo)', () {
    test('the canned response is internally consistent and matches the default request', () async {
      final repo = demoContainer().read(forecastRepositoryProvider);
      final request = await repo.defaultRequest();
      final response = await repo.compound(request);
      expect(response.matches(request), isTrue);
      expect(response.scenarios.keys, ForecastScenarioKind.values);
      for (final s in response.scenarios.values) {
        expect(s.nominal.first.year, 0);
        expect(s.nominal.last.year, request.years);
        expect(s.nominal.length, request.years + 1);
        expect(s.real.length, s.nominal.length);
        expect(
          s.finalNominal.amount,
          s.nominal.last.value,
          reason: s.kind.name,
        );
        expect(s.finalReal.amount, s.real.last.value, reason: s.kind.name);
        expect(
          s.totalContributions.amount + s.totalGrowth.amount,
          s.finalNominal.amount,
          reason: s.kind.name,
        );
        expect(s.finalReal.amount, lessThan(s.finalNominal.amount));
      }
      final r = response.scenarios;
      expect(
        r[ForecastScenarioKind.conservative]!.finalNominal.amount,
        lessThan(r[ForecastScenarioKind.base]!.finalNominal.amount),
      );
      expect(
        r[ForecastScenarioKind.base]!.finalNominal.amount,
        lessThan(r[ForecastScenarioKind.growth]!.finalNominal.amount),
      );
      expect(response.notice.toLowerCase(), contains('not guaranteed'));
    });

    test('a different request still returns the canned response, flagged as not matching', () async {
      final repo = demoContainer().read(forecastRepositoryProvider);
      final base = await repo.defaultRequest();
      final other = CompoundForecastRequest.fromJson(
        JsonReader({...base.toJson(), 'years': 10}),
      );
      final response = await repo.compound(other);
      expect(response.matches(other), isFalse);
      expect(response.matches(base), isTrue);
    });

    test('request JSON round-trips with strings only', () async {
      final request = await demoContainer()
          .read(forecastRepositoryProvider)
          .defaultRequest();
      final json = request.toJson();
      expect((json['initial_investment'] as Map)['amount'], isA<String>());
      expect(json['annual_return_percent'], isA<String>());
      expect(CompoundForecastRequest.fromJson(JsonReader(json)), request);
    });

    test('request equality is by decimal value', () async {
      final base = await demoContainer()
          .read(forecastRepositoryProvider)
          .defaultRequest();
      final same = CompoundForecastRequest.fromJson(
        JsonReader({...base.toJson(), 'annual_return_percent': '8'}),
      );
      expect(same, base);
      expect(same.hashCode, base.hashCode);
    });
  });

  group('CopilotRepository (demo)', () {
    Future<ChatTurn> play(
      CopilotRepository repo,
      String q, {
      AiScope? scope,
    }) async {
      var turn = ChatTurn(question: q);
      await for (final e in repo.ask(q, scope: scope)) {
        turn = turn.apply(e);
      }
      return turn;
    }

    test(
      'every suggested question has a full four-section answer with sources',
      () async {
        final repo = demoContainer().read(copilotRepositoryProvider);
        final questions = await repo.suggestedQuestions();
        expect(questions.length, greaterThanOrEqualTo(4));
        for (final q in questions) {
          final turn = await play(repo, q);
          expect(turn.done, isTrue, reason: q);
          expect(turn.failed || turn.refused, isFalse, reason: q);
          expect(
            turn.sections.map((s) => s.kind),
            SectionKind.values,
            reason: q,
          );
          expect(turn.sources, isNotEmpty, reason: q);
          expect(turn.progress, isNotEmpty, reason: q);
        }
      },
    );

    test('no scripted answer promises a return', () async {
      final repo = demoContainer().read(copilotRepositoryProvider);
      const banned = [
        'risk-free',
        'guaranteed to',
        'will definitely',
        'certain to',
        'sure thing',
        'you will earn',
      ];
      for (final q in await repo.suggestedQuestions()) {
        final text = (await play(
          repo,
          q,
        )).sections.map((s) => s.text.toLowerCase()).join(' ');
        for (final phrase in banned) {
          expect(text, isNot(contains(phrase)), reason: q);
        }
      }
    });

    test('the refusal script refuses', () async {
      final turn = await play(
        demoContainer().read(copilotRepositoryProvider),
        'Guarantee me a 20% return',
      );
      expect(turn.refused, isTrue);
      expect(turn.sections, isEmpty);
      expect(turn.done, isTrue);
    });

    test('the failure script ends in an error event', () async {
      final turn = await play(
        demoContainer().read(copilotRepositoryProvider),
        'Show me a failing request (demo)',
      );
      expect(turn.failed, isTrue);
      expect(turn.done, isTrue);
    });

    test(
      'an unscripted question gets the fixture reply and no invented advice',
      () async {
        final repo = demoContainer().read(copilotRepositoryProvider);
        final turn = await play(repo, 'What should I buy tomorrow?');
        expect(turn.sections, hasLength(1));
        expect(
          turn.sections.single.text,
          'Demo mode can answer the suggested questions only.',
        );
      },
    );

    test('matching ignores case and surrounding spaces', () async {
      final repo = demoContainer().read(copilotRepositoryProvider);
      final turn = await play(repo, '  HOW IS MY PORTFOLIO PERFORMING?  ');
      expect(turn.sections, hasLength(4));
    });

    test('a scope may be supplied', () async {
      final repo = demoContainer().read(copilotRepositoryProvider);
      final turn = await play(
        repo,
        'How is my portfolio performing?',
        scope: const AiScope(AiScopeKind.portfolio, 'p-retire'),
      );
      expect(turn.done, isTrue);
    });

    test('events arrive in order, spaced by the stream interval', () async {
      final repo = demoContainer(
        behavior: const DemoBehavior(
          latency: Duration.zero,
          streamInterval: Duration(milliseconds: 30),
        ),
      ).read(copilotRepositoryProvider);
      final stamps = <int>[];
      final watch = Stopwatch()..start();
      await for (final _ in repo.ask('How is my portfolio performing?')) {
        stamps.add(watch.elapsedMilliseconds);
      }
      expect(stamps.length, greaterThan(5));
      expect(stamps.last, greaterThanOrEqualTo(stamps.length * 25));
      expect(stamps, orderedEquals([...stamps]..sort()));
    });

    test(
      'failure injection surfaces as a stream error, then retry succeeds',
      () async {
        final container = demoContainer(
          behavior: DemoBehavior.instant.copyWith(failNextCalls: 1),
        );
        final repo = container.read(copilotRepositoryProvider);
        await expectLater(
          repo.ask('How is my portfolio performing?').toList(),
          throwsA(isA<DataLoadException>()),
        );
        final turn = await play(repo, 'How is my portfolio performing?');
        expect(turn.done, isTrue);
      },
    );

    test('intro and notice come from the fixture', () async {
      final intro = await demoContainer()
          .read(copilotRepositoryProvider)
          .intro();
      expect(intro.notice, contains('Demo responses'));
    });

    test('ChatEvent parsing rejects unknown types and section kinds', () {
      expect(
        () => ChatEvent.fromJson(JsonReader({'type': 'launch_missiles'})),
        throwsFormatException,
      );
      expect(
        () => ChatEvent.fromJson(
          JsonReader({'type': 'section', 'kind': 'gossip', 'text': 'x'}),
        ),
        throwsFormatException,
      );
    });
  });

  group('failure injection applies to every repository', () {
    test(
      'portfolio, dashboard and forecast calls fail while failAlways is on',
      () async {
        final c = demoContainer(
          behavior: DemoBehavior.instant.copyWith(failAlways: true),
        );
        await expectLater(
          c.read(portfolioRepositoryProvider).portfolios(),
          throwsA(isA<DataLoadException>()),
        );
        await expectLater(
          c.read(dashboardRepositoryProvider).netWorth(),
          throwsA(isA<DataLoadException>()),
        );
        final request = await c
            .read(forecastRepositoryProvider)
            .defaultRequest();
        await expectLater(
          c.read(forecastRepositoryProvider).compound(request),
          throwsA(isA<DataLoadException>()),
        );
      },
    );

    test('turning failure off restores data (retry)', () async {
      final c = demoContainer(
        behavior: DemoBehavior.instant.copyWith(failNextCalls: 1),
      );
      final repo = c.read(portfolioRepositoryProvider);
      await expectLater(repo.portfolios(), throwsA(isA<DataLoadException>()));
      expect(await repo.portfolios(), isNotEmpty);
    });
  });

  group('DashboardLayout', () {
    test('starts with every section visible in the default order', () {
      final layout = DashboardLayout.initial();
      expect(layout.order, DashboardSection.values);
      expect(layout.visible, DashboardSection.values);
    });

    test('move up and down, ignoring out-of-range moves', () {
      var layout = DashboardLayout.initial();
      layout = layout.move(DashboardSection.goals, -1);
      expect(layout.order, [
        DashboardSection.wealthSummary,
        DashboardSection.metrics,
        DashboardSection.goals,
        DashboardSection.insight,
      ]);
      expect(
        layout.move(DashboardSection.wealthSummary, -1).order,
        layout.order,
      );
      expect(layout.move(DashboardSection.insight, 1).order, layout.order);
    });

    test('hiding removes a section from visible but keeps its place', () {
      final layout = DashboardLayout.initial().withVisibility(
        DashboardSection.metrics,
        visible: false,
      );
      expect(layout.visible, isNot(contains(DashboardSection.metrics)));
      expect(layout.order, contains(DashboardSection.metrics));
      expect(
        layout.withVisibility(DashboardSection.metrics, visible: true).visible,
        DashboardSection.values,
      );
    });

    test('persists across a restart through the preferences store', () async {
      final store = InMemoryPreferencesStore();
      final first = LocalDashboardLayoutRepository(store);
      await first.save(
        DashboardLayout.initial()
            .move(DashboardSection.goals, -2)
            .withVisibility(DashboardSection.insight, visible: false),
      );
      final afterRestart = await LocalDashboardLayoutRepository(store).load();
      expect(afterRestart.order.first, DashboardSection.wealthSummary);
      expect(afterRestart.order[1], DashboardSection.goals);
      expect(afterRestart.hidden, {DashboardSection.insight});
    });

    test('corrupt or unknown stored data falls back safely', () async {
      for (final bad in ['{oops', '[]', '"x"', '{"order": 5}', '']) {
        expect(
          DashboardLayout.fromJsonString(bad).order,
          DashboardSection.values,
          reason: bad,
        );
      }
      final partial = DashboardLayout.fromJsonString(
        '{"order": ["goals", "bogus", "goals"], "hidden": ["bogus", "metrics"]}',
      );
      expect(partial.order.first, DashboardSection.goals);
      expect(
        partial.order.toSet(),
        DashboardSection.values.toSet(),
        reason: 'missing sections are appended',
      );
      expect(
        partial.order.length,
        DashboardSection.values.length,
        reason: 'no duplicates',
      );
      expect(partial.hidden, {DashboardSection.metrics});
    });

    test('a store without data returns the default layout', () async {
      expect(
        await LocalDashboardLayoutRepository(InMemoryPreferencesStore()).load(),
        DashboardLayout.initial(),
      );
    });
  });
}
