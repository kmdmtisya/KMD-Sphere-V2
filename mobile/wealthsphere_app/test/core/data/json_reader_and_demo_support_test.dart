import 'dart:convert';

import 'package:decimal/decimal.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/core/data/demo_support.dart';
import 'package:wealthsphere_app/core/data/json_reader.dart';

import '../../helpers/demo_container.dart';

class _MapBundle extends CachingAssetBundle {
  _MapBundle(this.files);

  final Map<String, String> files;

  @override
  Future<ByteData> load(String key) async {
    final text = files[key];
    if (text == null) throw StateError('missing $key');
    return ByteData.sublistView(Uint8List.fromList(utf8.encode(text)));
  }
}

void main() {
  group('JsonReader is strict', () {
    test('reads strings, integers, decimals and money', () {
      final r = JsonReader({
        's': 'x',
        'i': 3,
        'd': '12.50',
        'm': {'amount': '1234.50', 'currency': 'USD'},
        'b': true,
      });
      expect(r.string('s'), 'x');
      expect(r.integer('i'), 3);
      expect(r.decimal('d'), Decimal.parse('12.50'));
      expect(r.money('m').amount, Decimal.parse('1234.50'));
      expect(r.boolean('b'), isTrue);
    });

    test('rejects JSON numbers where decimals or money are expected', () {
      expect(() => JsonReader({'d': 12.5}).decimal('d'), throwsFormatException);
      expect(
        () => JsonReader({
          'm': {'amount': 10.5, 'currency': 'USD'},
        }).money('m'),
        throwsFormatException,
      );
    });

    test('rejects malformed decimals', () {
      for (final bad in ['1e5', '1,5', ' 1', '', 'abc', '1.', '.5', '--1']) {
        expect(
          () => JsonReader({'d': bad}).decimal('d'),
          throwsFormatException,
          reason: bad,
        );
      }
    });

    test('errors name the field path', () {
      final r = JsonReader({
        'a': {
          'b': {'amount': 5, 'currency': 'USD'},
        },
      });
      expect(
        () => r.object('a').money('b'),
        throwsA(
          isA<FormatException>().having(
            (e) => e.message,
            'message',
            contains(r'$.a.b'),
          ),
        ),
      );
      expect(
        () => r.object('a').string('missing'),
        throwsA(
          isA<FormatException>().having(
            (e) => e.message,
            'message',
            contains(r'$.a.missing is missing'),
          ),
        ),
      );
    });

    test('timestamps need a zone and are returned in UTC', () {
      expect(
        JsonReader({'t': '2026-10-09T08:00:00Z'}).timestamp('t'),
        DateTime.utc(2026, 10, 9, 8),
      );
      expect(
        JsonReader({'t': '2026-10-09T12:00:00+04:00'}).timestamp('t'),
        DateTime.utc(2026, 10, 9, 8),
      );
      expect(
        () => JsonReader({'t': '2026-10-09T08:00:00'}).timestamp('t'),
        throwsFormatException,
      );
      expect(
        () => JsonReader({'t': '2026-13-45T08:00:00Z'}).timestamp('t'),
        throwsFormatException,
      );
    });

    test('impossible calendar values are rejected, not rolled over', () {
      for (final bad in [
        '2026-02-30T08:00:00Z',
        '2026-13-01T08:00:00Z',
        '2026-10-09T24:00:00Z',
        '2026-10-09T08:60:00Z',
      ]) {
        expect(
          () => JsonReader({'t': bad}).timestamp('t'),
          throwsFormatException,
          reason: bad,
        );
      }
      expect(
        () => JsonReader({'d': '2026-02-29'}).date('d'),
        throwsFormatException,
      );
      expect(
        JsonReader({'d': '2028-02-29'}).date('d'),
        DateTime.utc(2028, 2, 29),
      );
    });

    test('dates are YYYY-MM-DD only', () {
      expect(
        JsonReader({'d': '2026-10-09'}).date('d'),
        DateTime.utc(2026, 10, 9),
      );
      expect(
        () => JsonReader({'d': '09/10/2026'}).date('d'),
        throwsFormatException,
      );
    });

    test('type mismatches and non-objects throw', () {
      expect(() => JsonReader([1]), throwsFormatException);
      expect(() => JsonReader({'i': '3'}).integer('i'), throwsFormatException);
      expect(
        () => JsonReader({'l': 'x'}).list('l', (r) => r),
        throwsFormatException,
      );
      expect(
        () => JsonReader({
          'l': [1],
        }).strings('l'),
        throwsFormatException,
      );
    });

    test('Decimal precision above 2^53 survives', () {
      const big = '9007199254740993.01';
      expect(JsonReader({'d': big}).decimal('d').toString(), big);
      expect(
        JsonReader({
          'm': {'amount': big, 'currency': 'USD'},
        }).money('m').toJson()['amount'],
        big,
      );
    });
  });

  group('DemoAssets', () {
    test('loads a file marked demo and caches it', () async {
      final assets = DemoAssets(
        _MapBundle({'assets/demo/a.json': '{"demo": true, "x": 1}'}),
      );
      expect((await assets.load('a.json'))['x'], 1);
      expect(await assets.load('a.json'), same(await assets.load('a.json')));
    });

    test('refuses files that are not marked demo', () async {
      final assets = DemoAssets(
        _MapBundle({
          'assets/demo/a.json': '{"x": 1}',
          'assets/demo/b.json': '{"demo": false}',
          'assets/demo/c.json': '[1]',
        }),
      );
      for (final f in ['a.json', 'b.json', 'c.json']) {
        await expectLater(
          assets.load(f),
          throwsA(isA<DemoDataException>()),
          reason: f,
        );
      }
    });

    test('reports invalid JSON and missing files', () async {
      final assets = DemoAssets(_MapBundle({'assets/demo/bad.json': '{oops'}));
      await expectLater(
        assets.load('bad.json'),
        throwsA(isA<DemoDataException>()),
      );
      await expectLater(
        assets.load('nope.json'),
        throwsA(isA<DemoDataException>()),
      );
    });
  });

  group('DemoBehavior', () {
    test('succeeds immediately by default in tests', () async {
      final c = demoContainer();
      await c.read(demoBehaviorProvider.notifier).gate();
    });

    test('waits for the configured latency', () async {
      final c = demoContainer(
        behavior: const DemoBehavior(latency: Duration(milliseconds: 80)),
      );
      final watch = Stopwatch()..start();
      await c.read(demoBehaviorProvider.notifier).gate();
      expect(watch.elapsedMilliseconds, greaterThanOrEqualTo(75));
    });

    test('failAlways fails every call', () async {
      final c = demoContainer(
        behavior: DemoBehavior.instant.copyWith(failAlways: true),
      );
      final gate = c.read(demoBehaviorProvider.notifier).gate;
      await expectLater(gate(), throwsA(isA<DataLoadException>()));
      await expectLater(gate(), throwsA(isA<DataLoadException>()));
    });

    test(
      'failNextCalls fails N calls and then recovers (retry works)',
      () async {
        final c = demoContainer(
          behavior: DemoBehavior.instant.copyWith(failNextCalls: 2),
        );
        final gate = c.read(demoBehaviorProvider.notifier).gate;
        await expectLater(gate(), throwsA(isA<DataLoadException>()));
        await expectLater(gate(), throwsA(isA<DataLoadException>()));
        await gate();
        expect(c.read(demoBehaviorProvider).failNextCalls, 0);
      },
    );

    test('the data source mode is demo', () {
      expect(demoContainer().read(dataSourceModeProvider), DataSourceMode.demo);
    });
  });
}
