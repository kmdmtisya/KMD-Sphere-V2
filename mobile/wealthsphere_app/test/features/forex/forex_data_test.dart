import 'dart:async';

import 'package:decimal/decimal.dart';
import 'package:fake_async/fake_async.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/app/app_routes.dart';
import 'package:wealthsphere_app/core/data/demo_support.dart';
import 'package:wealthsphere_app/core/data/json_reader.dart';
import 'package:wealthsphere_app/features/copilot/domain/chat_models.dart';
import 'package:wealthsphere_app/features/copilot/domain/conversation_models.dart';
import 'package:wealthsphere_app/features/forex/application/forex_alerts.dart';
import 'package:wealthsphere_app/features/forex/application/forex_providers.dart';
import 'package:wealthsphere_app/features/forex/data/forex_repository.dart';
import 'package:wealthsphere_app/features/forex/data/forex_stream.dart';
import 'package:wealthsphere_app/features/forex/data/live_forex_repository.dart';
import 'package:wealthsphere_app/features/forex/domain/forex_models.dart';
import 'package:wealthsphere_app/features/notifications/notification_service.dart';

import '../../helpers/demo_container.dart';
import '../../helpers/fake_api.dart';

/// The forex data layer (P13-T11): the DEMO fixture parses into every model, the live
/// repository calls the forex API with the right paths and queries and parses its answers, the
/// app never computes a figure, notices follow the user's settings, forex deep links are allowed,
/// and stream updates are batched so charts stay responsive (QG-19.2).
void main() {
  group('DEMO', () {
    late ForexRepository repo;
    setUp(() => repo = demoContainer().read(forexRepositoryProvider));

    test('quotes are simulated, and one is stale', () async {
      final board = await repo.quotes();
      expect(board.items, isNotEmpty);
      expect(board.items.every((q) => q.kind == PriceKind.simulated), isTrue);
      expect(
        board.items.where((q) => q.freshness == QuoteFreshness.stale),
        hasLength(1),
      );
      expect(board.notice, contains('DEMO'));
    });

    test('every section of the fixture parses', () async {
      expect(await repo.candles('EUR_USD', '1H'), hasLength(60));
      expect(await repo.candles('USD_KES', '1H'), isEmpty);
      expect((await repo.indicators('EUR_USD', '1H')).first.name, 'rsi');
      expect(await repo.levels('EUR_USD', '1H'), hasLength(2));
      final calibrated = await repo.forecast('EUR_USD', '4h');
      expect(calibrated.available && calibrated.calibrated, isTrue);
      expect(calibrated.modelVersion, 'demo-1');
      final uncalibrated = await repo.forecast('EUR_USD', '24h');
      expect(uncalibrated.calibrated, isFalse);
      expect((await repo.forecast('GBP_JPY', '1w')).available, isFalse);
      final ranking = await repo.opportunities();
      expect(ranking.items.map((o) => o.label).toSet(), {'Research candidate'});
      expect(await repo.opportunities(risk: 'low'), isA<ForexRanking>());
      expect((await repo.opportunities(risk: 'low')).items, hasLength(1));
      final events = await repo.calendar();
      expect(events.every((e) => e.demo), isTrue);
      final risk = await repo.calculateRisk(const {});
      expect(risk.lots, Decimal.parse('0.19'));
      expect(risk.disclosures.first, contains('gap or slip'));
      expect(await repo.backtests('EUR_USD'), hasLength(2));
      final accounts = await repo.paperAccounts();
      expect(accounts.single.startingBalanceIsDefault, isTrue);
      final positions = await repo.paperPositions(accounts.single.id);
      expect(positions.where((p) => p.open), hasLength(1));
      expect(
        await repo.paperPositions(accounts.single.id, status: 'closed'),
        hasLength(1),
      );
      final perf = await repo.paperPerformance(accounts.single.id);
      expect(perf.seriesNote, contains('never combined'));
    });

    test(
      'DEMO paper trading is read-only; journal notes stay in memory',
      () async {
        final order = PaperOrderRequest(
          instrument: 'EUR_USD',
          long: true,
          lots: Decimal.parse('0.1'),
          stop: Decimal.parse('1.08'),
        );
        expect(
          () => repo.placePaperOrder('demo-paper-1', order),
          throwsA(isA<DemoDataException>()),
        );
        expect(
          () => repo.openPaperAccount('x', 'USD'),
          throwsA(isA<DemoDataException>()),
        );
        expect(
          () => repo.closePaperPosition('demo-paper-1', 'demo-pos-1'),
          throwsA(isA<DemoDataException>()),
        );
        await repo.addJournalEntry('demo-paper-1', 'Waited for the close', [
          'plan',
        ]);
        final notes = await repo.journal('demo-paper-1');
        expect(notes.first.note, 'Waited for the close');
        expect(notes, hasLength(2));
      },
    );
  });

  group('live', () {
    final now = DateTime.utc(2026, 10, 9, 8);
    late FakeApi api;
    late LiveForexRepository repo;

    setUp(() {
      api = FakeApi();
      repo = LiveForexRepository(api.dio(), clock: () => now);
    });

    test(
      'candles, indicators and levels ask for a time window, never a figure',
      () async {
        api
          ..json('GET /api/v1/forex/candles', {
            'items': [
              {
                'ts': '2026-10-09T07:00:00Z',
                'open': '1.1',
                'high': '1.2',
                'low': '1.0',
                'close': '1.15',
                'data_type': 'simulated',
                'volume': null,
              },
            ],
          })
          ..json('GET /api/v1/forex/indicators', {
            'series': [
              {
                'name': 'rsi:14',
                'first_defined_index': 1,
                'outputs': {
                  'value': [null, '55.5', '61.42'],
                },
              },
              {
                'name': 'macd:12,26,9',
                'first_defined_index': 0,
                'outputs': {
                  'macd': ['0.1', '0.2'],
                  'histogram': ['0.01', null],
                },
              },
            ],
          })
          ..json('GET /api/v1/forex/structure', {
            'levels': [
              {
                'price': '1.0832',
                'role': 'support',
                'touches': 4,
                'first_ts': 'x',
                'last_ts': 'x',
                'established_ts': 'x',
              },
            ],
          });
        expect(
          (await repo.candles('EUR_USD', '1H')).single.close,
          Decimal.parse('1.15'),
        );
        final call = api.callsTo('GET', '/api/v1/forex/candles').single;
        expect(call.query['instrument'], 'EUR_USD');
        expect(call.query['end'], now.toIso8601String());
        expect(
          call.query['start'],
          now.subtract(const Duration(days: 7)).toIso8601String(),
        );
        final values = await repo.indicators('EUR_USD', '1H');
        expect(values.first.name, 'rsi:14');
        expect(
          values.first.value,
          Decimal.parse('61.42'),
        ); // the last defined value
        expect(
          values.firstWhere((v) => v.name.endsWith('.histogram')).value,
          Decimal.parse('0.01'),
        );
        expect((await repo.levels('EUR_USD', '1H')).single.touches, 4);
      },
    );

    test(
      'paper trading sends the request and parses the server answer',
      () async {
        api.on('POST /api/v1/forex/paper/accounts/a-1/orders', (call) {
          expect(call.body, {
            'instrument': 'EUR_USD',
            'side': 'short',
            'order_type': 'limit',
            'lots': '0.1',
            'stop': '1.09',
            'limit_price': '1.087',
          });
          return (
            201,
            {
              'order': {'status': 'pending'},
              'position': null,
              'warnings': [
                'The price is a simulated quote, not a tradable one.',
              ],
              'disclosures': [
                'A stop-loss does not guarantee the maximum loss.',
              ],
            },
          );
        });
        final placed = await repo.placePaperOrder(
          'a-1',
          PaperOrderRequest(
            instrument: 'EUR_USD',
            long: false,
            lots: Decimal.parse('0.1'),
            stop: Decimal.parse('1.09'),
            limitPrice: Decimal.parse('1.087'),
          ),
        );
        expect(placed.filled, isFalse);
        expect(placed.position, isNull);
        expect(placed.warnings.single, contains('simulated'));
      },
    );

    test(
      'an unknown route answers 404 like the forex flag being off',
      () async {
        expect(repo.quotes(), throwsA(anything));
      },
    );
  });

  group('notices and deep links', () {
    final now = DateTime.utc(2026, 10, 9, 12);
    ForexEvent event(String importance, Duration from) => ForexEvent(
      id: 'e',
      name: 'NFP',
      currencies: const ['USD'],
      importance: importance,
      scheduledAt: now.add(from),
      demo: true,
    );
    PaperPosition closed(Duration ago) => PaperPosition(
      id: 'p',
      instrument: 'EUR_USD',
      long: true,
      lots: Decimal.one,
      open: false,
      entryPrice: Decimal.one,
      entryAt: now,
      stop: Decimal.one,
      kind: PriceKind.simulated,
      exitAt: now.subtract(ago),
      exitReason: 'stop',
      realised: Decimal.parse('-10'),
    );

    test('high-importance events within the hour and recent paper exits', () {
      final notices = noticesFor(
        prefs: const ForexAlertPrefs(),
        events: [
          event('high', const Duration(minutes: 30)),
          event('high', const Duration(hours: 3)),
          event('medium', const Duration(minutes: 10)),
          event('high', const Duration(minutes: -5)),
        ],
        positions: [
          closed(const Duration(hours: 2)),
          closed(const Duration(days: 3)),
        ],
        now: now,
      );
      expect(notices.whereType<EventSoonNotice>().single.minutes, 30);
      expect(notices.whereType<PaperClosedNotice>(), hasLength(1));
      final off = noticesFor(
        prefs: const ForexAlertPrefs(eventReminders: false, paperExits: false),
        events: [event('high', const Duration(minutes: 30))],
        positions: [closed(const Duration(hours: 1))],
        now: now,
      );
      expect(off, isEmpty);
    });

    test('settings round-trip and tolerate a corrupt value', () {
      const p = ForexAlertPrefs(eventReminders: false);
      final back = ForexAlertPrefs.decode(p.encode());
      expect(back.eventReminders, isFalse);
      expect(back.paperExits, isTrue);
      expect(ForexAlertPrefs.decode('not json').eventReminders, isTrue);
      expect(ForexAlertPrefs.decode(null).paperExits, isTrue);
    });

    test('notifications may open the forex screens, nothing else new', () {
      for (final route in [
        AppRoutes.forex,
        AppRoutes.forexCalendar,
        AppRoutes.forexPaper,
      ]) {
        expect(NotificationRoute.fromPayload({'route': route})?.path, route);
      }
      expect(
        NotificationRoute.fromPayload({'route': AppRoutes.forexRisk}),
        isNull,
      );
      expect(
        NotificationRoute.fromPayload({
          'route': 'https://evil.test${AppRoutes.forex}',
        }),
        isNull,
      );
    });
  });

  test(
    'the Copilot shows the server-built sources of a forex answer (P13-T10)',
    () {
      final sections = sectionsFromStructured(
        JsonReader({
          'observed': [
            {'text': 'EUR/USD was bid at 1.0861.', 'source': 'get_forex_quote'},
          ],
          'interpretation': 'A snapshot of the feed.',
          'caveats': ['Forex prices come from the simulated development feed.'],
          'sources': [
            {
              'tool': 'get_forecast',
              'as_of': '2026-10-09T08:00:00Z',
              'data_types': ['simulated'],
              'model': 'lightgbm v14',
              'generated_at': '2026-10-09T08:00:00Z',
            },
          ],
        }),
      );
      final source = sections.singleWhere((s) => s.kind == SectionKind.source);
      expect(
        source.text,
        'get_forecast · as of 2026-10-09T08:00:00Z · simulated · model lightgbm v14 · '
        'generated 2026-10-09T08:00:00Z',
      );
      expect(sections.last.kind, SectionKind.source);
    },
  );

  test(
    'stream updates are batched into one state change per flush (QG-19.2)',
    () {
      fakeAsync((async) {
        final stream = _ManualStream();
        final container = ProviderContainer(
          overrides: [
            forexStreamProvider.overrideWithValue(stream),
            quoteBoardProvider.overrideWith(
              (ref) async => const QuoteBoard(
                feedStatus: 'connected',
                items: [],
                notice: '',
              ),
            ),
          ],
        );
        addTearDown(container.dispose);
        var changes = 0;
        container.listen(
          liveQuotesProvider,
          (_, _) => changes++,
          fireImmediately: false,
        );
        async.flushMicrotasks();
        for (var i = 0; i < 50; i++) {
          stream.push(_quote('EUR_USD', '1.08$i'));
          async.elapse(const Duration(milliseconds: 4));
        }
        async.elapse(LiveQuotesNotifier.flushEvery);
        expect(changes, lessThanOrEqualTo(2));
        expect(
          container.read(liveQuotesProvider)['EUR_USD']!.mid,
          Decimal.parse('1.0849'),
        );
      });
    },
  );
}

ForexQuote _quote(String instrument, String mid) => ForexQuote(
  instrument: instrument,
  freshness: QuoteFreshness.fresh,
  kind: PriceKind.simulated,
  mid: Decimal.parse(mid),
);

class _ManualStream implements ForexQuoteStream {
  final _quotes = StreamController<ForexQuote>.broadcast(sync: true);

  void push(ForexQuote q) => _quotes.add(q);

  @override
  Stream<ForexQuote> get quotes => _quotes.stream;

  @override
  Stream<StreamState> get states => const Stream.empty();

  @override
  StreamState get state => StreamState.live;

  @override
  void follow(Set<String> instruments) {}

  @override
  Future<void> start() async {}

  @override
  Future<void> pause() async {}

  @override
  Future<void> resume() async {}

  @override
  Future<void> dispose() async {}
}
