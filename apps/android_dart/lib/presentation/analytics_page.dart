import 'package:flutter/material.dart';
import '../domain/analytics.dart';
import '../domain/provider.dart';
import 'controls.dart';
import 'theme.dart';

class AnalyticsPage extends StatefulWidget {
  const AnalyticsPage({
    super.key,
    required this.t,
    required this.rows,
    required this.money,
    this.languagePicker,
  });
  final Translate t;
  final List<Attempt> rows;
  final bool money;
  final Widget? languagePicker;
  @override
  State<AnalyticsPage> createState() => _AnalyticsPageState();
}

class _AnalyticsPageState extends State<AnalyticsPage> {
  String provider = 'all', model = 'all';
  int days = 7;
  @override
  Widget build(BuildContext context) {
    final t = widget.t, now = DateTime.now();
    final records = widget.rows.where(
      (r) => provider == 'all' || r['provider'] == provider,
    );
    final period = ChartPeriod.forFilter(now, days == 0 ? null : days, records);
    final models =
        records
            .where((r) => days == 0 || period.contains(r))
            .map(modelKey)
            .toSet()
            .toList()
          ..sort();
    if (!models.contains(model)) model = 'all';
    final series = daily(
      widget.rows,
      provider: provider,
      model: model,
      days: days == 0 ? null : days,
      now: now,
      money: widget.money,
    );
    final summaries = <String, DayUsage>{};
    final byProvider = <String, DayUsage>{};
    for (final row in records) {
      if ((days != 0 && !period.contains(row)) ||
          (model != 'all' && modelKey(row) != model)) {
        continue;
      }
      if (!widget.money) {
        final service = row['provider'] as String;
        (byProvider[service] ??= DayUsage('', '')).add(row);
      }
      final group = widget.money ? row['currency'] as String : modelKey(row);
      (summaries[group] ??= DayUsage('', widget.money ? group : '')).add(row);
    }
    final topModels =
        summaries.entries.where((e) => e.value.apiTotalsReported > 0).toList()
          ..sort((a, b) {
            final comparison = b.value.apiTokens.compareTo(a.value.apiTokens);
            return comparison != 0 ? comparison : a.key.compareTo(b.key);
          });
    final currencies = widget.money
        ? (series.map((d) => d.currency).toSet().toList()..sort())
        : [''];
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        pageHeading(
          t(
            widget.money
                ? 'analytics.title.spending'
                : 'analytics.title.tokens',
          ),
          widget.languagePicker,
        ),
        const SizedBox(height: 12),
        Text(t('analytics.scope')),
        const SizedBox(height: 12),
        LayoutBuilder(
          builder: (context, bounds) {
            final wide = MediaQuery.sizeOf(context).width >= 768;
            final width = wide ? (bounds.maxWidth - 20) / 3 : bounds.maxWidth;
            final filters = [
              PageFilter<String>(
                label: t('analytics.provider'),
                value: provider,
                options: {
                  'all': t('common.provider_all'),
                  for (final s in Service.values) s.name: s.label,
                },
                onSelected: (v) => setState(() {
                  provider = v;
                  model = 'all';
                }),
              ),
              PageFilter<int>(
                label: t('analytics.period'),
                value: days,
                options: {
                  for (final d in [7, 30, 0])
                    d: t('analytics.period.${d == 0 ? 'all' : '${d}d'}'),
                },
                onSelected: (v) => setState(() => days = v),
              ),
              PageFilter<String>(
                label: t('analytics.model'),
                value: model,
                options: {
                  'all': t('analytics.all_models'),
                  for (final m in models) m: m,
                },
                onSelected: (v) => setState(() => model = v),
              ),
            ];
            return Wrap(
              spacing: 10,
              runSpacing: 10,
              children: [
                for (final filter in filters)
                  SizedBox(width: width, child: filter),
              ],
            );
          },
        ),
        const SizedBox(height: 12),
        Text(
          interpolate(t('analytics.timezone'), {'timezone': now.timeZoneName}),
          style: const TextStyle(color: muted),
        ),
        if (widget.money)
          Text(
            t('analytics.spending_sources'),
            style: const TextStyle(color: muted),
          ),
        if (widget.money && currencies.isEmpty) Text(t('analytics.empty')),
        for (final currency in currencies)
          Padding(
            padding: const EdgeInsets.only(top: 16),
            child: panelCard([
              Text(
                widget.money
                    ? interpolate(t('analytics.currency_panel'), {
                        'provider': currency == 'USD' ? 'OpenRouter' : 'VSEGPT',
                        'currency': currency,
                      })
                    : t('analytics.tokens_by_day'),
                style: Theme.of(context).textTheme.titleLarge,
              ),
              _DayChart(
                key: ValueKey((provider, model, days, currency)),
                t: t,
                period: period,
                currency: currency,
                money: widget.money,
                rows: series
                    .where((d) => d.currency == currency && d.date.isNotEmpty)
                    .toList(),
              ),
              if (widget.money && summaries[currency] != null)
                _DayDetail(
                  t: t,
                  row: summaries[currency],
                  money: true,
                  title: t('analytics.actual_total'),
                ),
              for (final row in series.where(
                (d) => d.currency == currency && d.date.isEmpty,
              ))
                _DayDetail(
                  t: t,
                  row: row,
                  money: widget.money,
                  title: interpolate(t('analytics.undated'), {
                    'count': row.attempts,
                  }),
                ),
            ]),
          ),
        if (!widget.money) ...[
          if (summaries.isEmpty) Text(t('analytics.empty')),
          for (final service in Service.values)
            if (byProvider[service.name] case final totals?)
              _DayDetail(t: t, row: totals, money: false, title: service.label),
          if (topModels.isNotEmpty)
            Text(
              t('analytics.top_models'),
              style: Theme.of(context).textTheme.titleMedium,
            ),
          for (final group in topModels.take(5))
            ListTile(
              contentPadding: EdgeInsets.zero,
              title: Text(
                interpolate(t('analytics.model_usage'), {
                  'provider': Service.values
                      .byName(group.key.split('/').first)
                      .label,
                  'model': group.key.substring(group.key.indexOf('/') + 1),
                  'tokens': group.value.apiTokens,
                }),
              ),
              subtitle: LinearProgressIndicator(
                value: topModels.first.value.apiTokens == 0
                    ? 0
                    : group.value.apiTokens / topModels.first.value.apiTokens,
              ),
            ),
        ],
      ],
    );
  }
}

class _DayDetail extends StatelessWidget {
  const _DayDetail({
    required this.t,
    required this.row,
    required this.money,
    required this.title,
  });
  final Translate t;
  final DayUsage? row;
  final bool money;
  final String title;
  @override
  Widget build(BuildContext context) {
    final d = row;
    final lines = d == null
        ? [t('analytics.day_no_requests')]
        : money
        ? [
            "${t('analytics.actual')} · ${d.confirmedCosts == 0 && d.unknownCost > 0 ? t('analytics.unknown') : '${d.confirmed} ${d.currency}'}",
            "${t('analytics.estimated')} · ${d.estimated} ${d.currency}",
            if (d.unknownCost > 0)
              interpolate(t('analytics.unknown_costs'), {
                'count': d.unknownCost,
              }),
          ]
        : [
            "${t('analytics.requests')} ${d.attempts}",
            "${t('analytics.api_requests')} ${d.apiRequests}",
            "${t('analytics.unknown_requests')} ${d.unknownRequests}",
            "${t('analytics.token_input')} ${d.apiInputsReported > 0 ? d.apiInput : t('analytics.unknown')} · ${t('analytics.token_output')} ${d.apiOutputsReported > 0 ? d.apiOutput : t('analytics.unknown')}",
            "${t('analytics.api_total')} ${d.apiTotalsReported > 0 ? d.apiTokens : t('analytics.unknown')}",
            if (d.estimatedTokens > 0)
              interpolate(t('analytics.estimated_tokens'), {
                'input': d.estimateInput,
                'output': d.estimateOutput,
                'total': d.estimatedTokens,
              }),
            if (d.partial > 0)
              interpolate(t('analytics.token_partial_day'), {
                'count': d.partial,
              }),
          ];
    return ListTile(
      contentPadding: EdgeInsets.zero,
      title: Text(title),
      subtitle: Text(lines.join('\n')),
    );
  }
}

class _DayChart extends StatefulWidget {
  const _DayChart({
    super.key,
    required this.t,
    required this.period,
    required this.currency,
    required this.rows,
    required this.money,
  });
  final Translate t;
  final ChartPeriod period;
  final String currency;
  final List<DayUsage> rows;
  final bool money;
  @override
  State<_DayChart> createState() => _DayChartState();
}

class _DayChartState extends State<_DayChart> {
  String? selection;
  void select(int index) =>
      setState(() => selection = widget.period.label(index));
  @override
  Widget build(BuildContext context) {
    final t = widget.t, period = widget.period, money = widget.money;
    final byDay = {for (final r in widget.rows) r.date: r};
    final chosen =
        selection ??
        (widget.rows.lastOrNull?.date ?? period.label(period.length - 1));
    final index = period.index(chosen).clamp(0, period.length - 1);
    final visible = period.length.clamp(1, 31);
    final start = (index - visible ~/ 2).clamp(0, period.length - visible);
    double value(DayUsage? d, bool estimate) {
      if (d == null) return 0;
      return money
          ? double.parse((estimate ? d.estimated : d.confirmed).toString())
          : (estimate ? d.estimatedTokens : d.apiTokens).toDouble();
    }

    double maximum = 0;
    for (var i = start; i < start + visible; i++) {
      final d = byDay[period.label(i)];
      for (final v in [value(d, false), value(d, true)]) {
        if (v > maximum) maximum = v;
      }
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Wrap(
          spacing: 16,
          children: [
            Text(
              t(money ? 'analytics.actual' : 'analytics.token_source.api'),
              style: const TextStyle(color: primary),
            ),
            Text(
              t(
                money
                    ? 'analytics.estimated'
                    : 'analytics.token_source.estimate',
              ),
              style: const TextStyle(color: Colors.amber),
            ),
          ],
        ),
        const SizedBox(height: 8),
        Text(
          t(
            money ? 'analytics.chart_accessible' : 'analytics.token_chart_help',
          ).replaceAll('{currency}', widget.currency),
          style: const TextStyle(fontSize: 12, color: muted),
        ),
        if (!money && maximum == 0)
          Text(
            t('analytics.token_chart_no_totals'),
            style: const TextStyle(fontSize: 12, color: muted),
          ),
        SizedBox(
          height: 140,
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              for (var i = start; i < start + visible; i++)
                Expanded(
                  child: Semantics(
                    label: period.label(i),
                    selected: i == index,
                    button: true,
                    child: InkWell(
                      onTap: () => select(i),
                      child: ColoredBox(
                        color: i == index
                            ? primary.withValues(alpha: .10)
                            : Colors.transparent,
                        child: Stack(
                          alignment: Alignment.bottomCenter,
                          children: [
                            Row(
                              crossAxisAlignment: CrossAxisAlignment.end,
                              children: [
                                for (final estimate in [false, true])
                                  Expanded(
                                    child: FractionallySizedBox(
                                      widthFactor: .75,
                                      child: SizedBox(
                                        height: maximum == 0
                                            ? 0
                                            : (value(
                                                        byDay[period.label(i)],
                                                        estimate,
                                                      ) /
                                                      maximum *
                                                      112)
                                                  .clamp(0, 112),
                                        child: ColoredBox(
                                          color: estimate
                                              ? Colors.amber
                                              : primary,
                                        ),
                                      ),
                                    ),
                                  ),
                              ],
                            ),
                            if ((money
                                    ? byDay[period.label(i)]?.unknownCost
                                    : byDay[period.label(i)]?.partial)
                                case final int missing when missing > 0)
                              const Positioned(
                                top: 3,
                                child: Icon(
                                  Icons.circle,
                                  size: 6,
                                  color: muted,
                                ),
                              ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
            ],
          ),
        ),
        Text(
          interpolate(t('analytics.token_chart_range'), {
            'start': period.label(start),
            'end': period.label(start + visible - 1),
          }),
          style: const TextStyle(color: muted, fontSize: 12),
        ),
        if (period.length > 1)
          Row(
            children: [
              IconButton(
                tooltip: t('analytics.previous_day'),
                onPressed: index == 0 ? null : () => select(index - 1),
                icon: const Icon(Icons.chevron_left),
              ),
              Expanded(
                child: Slider(
                  value: index.toDouble(),
                  max: (period.length - 1).toDouble(),
                  divisions: period.length - 1,
                  semanticFormatterCallback: (v) => period.label(v.round()),
                  onChanged: (v) => select(v.round()),
                ),
              ),
              IconButton(
                tooltip: t('analytics.next_day'),
                onPressed: index == period.length - 1
                    ? null
                    : () => select(index + 1),
                icon: const Icon(Icons.chevron_right),
              ),
            ],
          ),
        _DayDetail(
          t: t,
          row: byDay[period.label(index)],
          title: period.label(index),
          money: money,
        ),
      ],
    );
  }
}
