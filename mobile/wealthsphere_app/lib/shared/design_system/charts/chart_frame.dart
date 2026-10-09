import 'package:flutter/material.dart';

import '../../../l10n/generated/app_localizations.dart';
import '../components/state_views.dart';
import '../theme/wealth_typography.dart';
import '../tokens/tokens.dart';

/// Wraps a chart so that it is accessible:
/// - screen readers get [summary] instead of the drawing;
/// - a "View as table" toggle shows the same data as text ([tableHeaders] and [tableRows]);
/// - an empty chart shows a message instead of an empty box.
class ChartFrame extends StatefulWidget {
  const ChartFrame({
    required this.summary,
    required this.chart,
    required this.tableHeaders,
    required this.tableRows,
    this.height = 200,
    this.isEmpty = false,
    super.key,
  });

  final String summary;
  final Widget chart;
  final List<String> tableHeaders;
  final List<List<String>> tableRows;
  final double height;
  final bool isEmpty;

  @override
  State<ChartFrame> createState() => _ChartFrameState();
}

class _ChartFrameState extends State<ChartFrame> {
  bool _table = false;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    if (widget.isEmpty) {
      return SizedBox(
        height: widget.height,
        child: EmptyState(
          title: l10n.chartNoData,
          icon: Icons.show_chart_rounded,
        ),
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        if (_table)
          _ChartTable(
            height: widget.height,
            headers: widget.tableHeaders,
            rows: widget.tableRows,
          )
        else
          Semantics(
            image: true,
            label: widget.summary,
            excludeSemantics: true,
            child: SizedBox(height: widget.height, child: widget.chart),
          ),
        Align(
          alignment: AlignmentDirectional.centerStart,
          child: TextButton(
            onPressed: () => setState(() => _table = !_table),
            child: Text(_table ? l10n.chartViewAsChart : l10n.chartViewAsTable),
          ),
        ),
      ],
    );
  }
}

class _ChartTable extends StatelessWidget {
  const _ChartTable({
    required this.height,
    required this.headers,
    required this.rows,
  });

  final double height;
  final List<String> headers;
  final List<List<String>> rows;

  @override
  Widget build(BuildContext context) {
    final text = context.wealthText;
    final colors = context.wealthColors;
    Widget line(List<String> cells, TextStyle style) => Padding(
      padding: const EdgeInsetsDirectional.symmetric(vertical: AppSpacing.xxs),
      child: Row(
        children: [
          for (final c in cells) Expanded(child: Text(c, style: style)),
        ],
      ),
    );
    return SizedBox(
      height: height,
      child: Column(
        children: [
          line(headers, text.label.copyWith(color: colors.textMuted)),
          const Divider(height: 1),
          Expanded(
            child: ListView.builder(
              itemCount: rows.length,
              itemBuilder: (_, i) => line(rows[i], text.body),
            ),
          ),
        ],
      ),
    );
  }
}
