import 'package:decimal/decimal.dart';
import 'package:flutter/material.dart';

import '../../shared/design_system/charts/charts.dart';
import '../../shared/design_system/components/components.dart';
import '../../shared/design_system/formatting/formatting.dart';
import '../../shared/design_system/tokens/tokens.dart';

/// One titled group of components in the gallery. [builder] gets [animated] = false when the
/// content must hold still (golden images).
class GallerySection {
  const GallerySection({
    required this.id,
    required this.title,
    required this.builder,
  });

  final String id;
  final String title;
  final Widget Function(BuildContext context, {required bool animated}) builder;
}

// All figures below are illustrative DEMO fixtures, never real or live data.
final DateTime _now = DateTime.utc(2026, 10, 9, 12);
Money _usd(String a) => Money.parse(a, 'USD');
Decimal _d(String v) => Decimal.parse(v);

const double _gap = AppSpacing.m;

Widget _stack(List<Widget> children) => Column(
  crossAxisAlignment: CrossAxisAlignment.start,
  children: [
    for (var i = 0; i < children.length; i++) ...[
      if (i > 0) const SizedBox(height: _gap),
      children[i],
    ],
  ],
);

ChartPoint _pt(int month, String y) =>
    ChartPoint(DateTime.utc(2026, month, 1), _d(y));

final ChartSeries _demoSeries = ChartSeries(
  id: 'demo',
  label: 'Portfolio value',
  currencyCode: 'USD',
  points: [
    _pt(1, '100000'),
    _pt(2, '104500'),
    _pt(3, '101200'),
    _pt(4, '110800'),
    _pt(5, '118300'),
    _pt(6, '121900'),
  ],
);

final List<AllocationSlice> _demoSlices = [
  AllocationSlice(id: 'eq', label: 'Equities', percent: _d('52')),
  AllocationSlice(id: 'bd', label: 'Bonds', percent: _d('23')),
  AllocationSlice(id: 'cs', label: 'Cash', percent: _d('10')),
  AllocationSlice(id: 're', label: 'Real estate', percent: _d('15')),
];

List<ForecastSeries> get _demoForecast => [
  for (final (id, label, end) in [
    ('cons', 'Conservative', '150000'),
    ('base', 'Base', '210000'),
    ('grow', 'Growth', '300000'),
  ])
    ForecastSeries(
      id: id,
      label: label,
      currencyCode: 'USD',
      points: [ForecastPoint(0, _d('100000')), ForecastPoint(10, _d(end))],
    ),
];

class _ScenarioDemo extends StatefulWidget {
  const _ScenarioDemo();

  @override
  State<_ScenarioDemo> createState() => _ScenarioDemoState();
}

class _ScenarioDemoState extends State<_ScenarioDemo> {
  int _selected = 1;

  @override
  Widget build(BuildContext context) {
    const names = ['Conservative', 'Base', 'Growth'];
    const rates = ['4', '7', '10'];
    const values = ['150000', '210000', '300000'];
    return _stack([
      for (var i = 0; i < 3; i++)
        ScenarioCard(
          name: names[i],
          annualReturnPercent: _d(rates[i]),
          finalValue: _usd(values[i]),
          selected: i == _selected,
          onSelected: () => setState(() => _selected = i),
        ),
    ]);
  }
}

class _PeriodDemo extends StatefulWidget {
  const _PeriodDemo();

  @override
  State<_PeriodDemo> createState() => _PeriodDemoState();
}

class _PeriodDemoState extends State<_PeriodDemo> {
  ChartPeriod _period = ChartPeriod.month;

  @override
  Widget build(BuildContext context) => PeriodSelector(
    periods: const [
      ChartPeriod.week,
      ChartPeriod.month,
      ChartPeriod.yearToDate,
      ChartPeriod.year,
      ChartPeriod.all,
    ],
    selected: _period,
    onChanged: (p) => setState(() => _period = p),
  );
}

/// Every design-system component, grouped. The gallery screen and the golden tests both read
/// this list, so a component added here appears in both.
final List<GallerySection> gallerySections = [
  GallerySection(
    id: 'amounts',
    title: 'Amounts, change and risk',
    builder: (context, {required animated}) => _stack([
      CurrencyAmount(money: _usd('1234567.89')),
      CurrencyAmount(money: _usd('-1234.50')),
      CurrencyAmount(
        money: _usd('1000.00'),
        nativeMoney: Money.parse('3673.00', 'AED'),
      ),
      CurrencyAmount(money: _usd('1234567.89'), compact: true),
      ChangeIndicator(percent: _d('2.5'), periodLabel: 'today'),
      ChangeIndicator(percent: _d('-1.25'), amount: _usd('-125.00')),
      ChangeIndicator(percent: _d('0')),
      const Wrap(
        spacing: AppSpacing.xs,
        runSpacing: AppSpacing.xs,
        children: [
          RiskLabel(level: RiskLevel.low),
          RiskLabel(level: RiskLevel.medium),
          RiskLabel(level: RiskLevel.high),
        ],
      ),
    ]),
  ),
  GallerySection(
    id: 'status',
    title: 'Status and disclosure',
    builder: (context, {required animated}) => _stack([
      const DemoBadge(),
      const DemoBanner(),
      OfflineBanner(onRetry: () {}),
      StaleDataBanner(
        asOf: _now.subtract(const Duration(hours: 5)),
        now: _now,
        onRetry: () {},
      ),
      DataAsOfLabel(asOf: _now.subtract(const Duration(hours: 2)), now: _now),
      const DisclosurePanel(
        title: 'How is this calculated?',
        summary: 'Illustrative projection. It is not a guarantee of returns.',
        details: Text(
          'Assumes a constant annual return and regular monthly contributions.',
        ),
      ),
    ]),
  ),
  GallerySection(
    id: 'states',
    title: 'Loading, empty and error',
    builder: (context, {required animated}) => _stack([
      SkeletonLoader(animate: animated, child: const _SkeletonCard()),
      const EmptyState(actionLabel: 'Add holding'),
      ErrorState(onRetry: () {}),
    ]),
  ),
  GallerySection(
    id: 'cards',
    title: 'Cards',
    builder: (context, {required animated}) => _stack([
      WealthSummaryCard(
        label: 'Total wealth',
        amount: CurrencyAmount(
          money: _usd('121900'),
          style: Theme.of(context).textTheme.headlineMedium,
        ),
        change: ChangeIndicator(percent: _d('3.1'), periodLabel: 'this month'),
        footer: DataAsOfLabel(
          asOf: _now.subtract(const Duration(minutes: 5)),
          now: _now,
        ),
      ),
      MetricCard(
        icon: Icons.savings_outlined,
        label: 'Passive income',
        value: CurrencyAmount(money: _usd('1250.00')),
        subValue: 'per month, estimated',
        definition: 'Income expected from dividends and interest.',
      ),
    ]),
  ),
  GallerySection(
    id: 'selectors',
    title: 'Selectors and scenarios',
    builder: (context, {required animated}) => _stack([
      const _PeriodDemo(),
      PortfolioSwitcher(
        portfolios: [
          PortfolioOption(id: 'a', name: 'Retirement', value: _usd('90000.00')),
          PortfolioOption(id: 'b', name: 'Growth', value: _usd('31900.00')),
        ],
        selectedId: 'a',
        consolidatedValue: _usd('121900.00'),
        onSelected: (_) {},
      ),
      const _ScenarioDemo(),
    ]),
  ),
  GallerySection(
    id: 'rows',
    title: 'Rows and evidence',
    builder: (context, {required animated}) => _stack([
      InvestmentRow(
        symbol: 'DEMO1',
        name: 'Demo Global Equity Fund',
        value: _usd('15000.00'),
        changePercent: _d('1.5'),
      ),
      InvestmentRow(
        symbol: 'DEMO2',
        name: 'Demo Regional Bond',
        value: _usd('9800.00'),
        nativeValue: Money.parse('36000.00', 'AED'),
        changePercent: _d('-0.4'),
        changeAmount: _usd('-39.20'),
      ),
      EvidenceSourceChip(
        source: EvidenceSource(
          label: 'Price feed (demo)',
          provider: 'Demo Data Co.',
          asOf: _now.subtract(const Duration(hours: 3)),
        ),
        now: _now,
      ),
    ]),
  ),
  GallerySection(
    id: 'navigation',
    title: 'Navigation and input',
    builder: (context, {required animated}) => _stack([
      WealthBottomNav(
        destinations: const [
          WealthNavDestination(
            icon: Icons.home_outlined,
            selectedIcon: Icons.home,
            label: 'Home',
          ),
          WealthNavDestination(
            icon: Icons.pie_chart_outline,
            selectedIcon: Icons.pie_chart,
            label: 'Portfolio',
          ),
          WealthNavDestination(
            icon: Icons.auto_awesome_outlined,
            selectedIcon: Icons.auto_awesome,
            label: 'AI Wealth',
          ),
          WealthNavDestination(
            icon: Icons.flag_outlined,
            selectedIcon: Icons.flag,
            label: 'Goals',
          ),
          WealthNavDestination(
            icon: Icons.more_horiz,
            selectedIcon: Icons.more_horiz,
            label: 'More',
          ),
        ],
        selectedIndex: 0,
        onSelected: (_) {},
      ),
      AIChatComposer(onSend: (_) {}),
      AIChatComposer(onSend: (_) {}, streaming: true, onStop: () {}),
    ]),
  ),
  GallerySection(
    id: 'charts',
    title: 'Charts',
    builder: (context, {required animated}) => _stack([
      PerformanceLineChart(series: _demoSeries, rangeLabel: '6 months'),
      AllocationDonutChart(slices: _demoSlices, centre: const Text('Mix')),
      ForecastComparisonChart(series: _demoForecast, selectedId: 'base'),
    ]),
  ),
];

class _SkeletonCard extends StatelessWidget {
  const _SkeletonCard();

  @override
  Widget build(BuildContext context) => const Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      SkeletonBox(width: 120, height: 14),
      SizedBox(height: AppSpacing.xs),
      SkeletonBox(height: 32),
      SizedBox(height: AppSpacing.xs),
      SkeletonBox(width: 200, height: 14),
    ],
  );
}
