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
  });
  final Translate t;
  final List<Attempt> rows;
  final bool money;
  @override
  State<AnalyticsPage> createState() => _AnalyticsPageState();
}

class _AnalyticsPageState extends State<AnalyticsPage> {
  String provider = 'all', model = 'all';
  int days = 7;
  String? selected;
  @override
  Widget build(BuildContext context) {
    final t = widget.t;
    final models =
        widget.rows
            .where((r) => provider == 'all' || r['provider'] == provider)
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
      now: DateTime.now(),
      money: widget.money,
    );
    final currencies = widget.money
        ? [
            for (final s in Service.values)
              if (provider == 'all' || provider == s.name) s.currency,
          ]
        : [''];
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text(
          t(
            widget.money
                ? 'analytics.title.spending'
                : 'analytics.title.tokens',
          ),
          style: Theme.of(context).textTheme.headlineMedium,
        ),
        Text(t('analytics.scope')),
        const SizedBox(height: 12),
        panelCard([
          DropdownButtonFormField<String>(
            initialValue: provider,
            decoration: InputDecoration(labelText: t('analytics.provider')),
            items: [
              DropdownMenuItem(
                value: 'all',
                child: Text(t('common.provider_all')),
              ),
              for (final s in Service.values)
                DropdownMenuItem(value: s.name, child: Text(s.label)),
            ],
            onChanged: (s) => setState(() {
              provider = s ?? 'all';
              model = 'all';
              selected = null;
            }),
          ),
          DropdownButtonFormField<int>(
            initialValue: days,
            decoration: InputDecoration(labelText: t('analytics.period')),
            items: [
              for (final d in [7, 30, 0])
                DropdownMenuItem(
                  value: d,
                  child: Text(
                    t('analytics.period.${d == 0 ? 'all' : '${d}d'}'),
                  ),
                ),
            ],
            onChanged: (d) => setState(() {
              days = d ?? 7;
              selected = null;
            }),
          ),
          DropdownButtonFormField<String>(
            key: ValueKey((provider, model)),
            initialValue: model,
            isExpanded: true,
            decoration: InputDecoration(labelText: t('analytics.model')),
            items: [
              DropdownMenuItem(
                value: 'all',
                child: Text(t('analytics.all_models')),
              ),
              for (final m in models)
                DropdownMenuItem(
                  value: m,
                  child: Text(m, overflow: TextOverflow.ellipsis),
                ),
            ],
            onChanged: (m) => setState(() {
              model = m ?? 'all';
              selected = null;
            }),
          ),
        ]),
        for (final currency in currencies)
          Padding(
            padding: const EdgeInsets.only(top: 16),
            child: panelCard([
              Text(
                currency.isEmpty
                    ? t('analytics.title.tokens')
                    : interpolate(t('analytics.currency_panel'), {
                        'provider': currency == 'USD' ? 'OpenRouter' : 'VSEGPT',
                        'currency': currency,
                      }),
              ),
              if (series.where((d) => d.currency == currency).isEmpty)
                Text(t('analytics.empty'))
              else ...[
                _Bars(
                  series: series
                      .where((d) => d.currency == currency && d.date.isNotEmpty)
                      .toList(),
                  t: t,
                  money: widget.money,
                  selected: selected,
                  onSelect: (date) => setState(() => selected = date),
                ),
                for (final d in series.where(
                  (d) =>
                      d.currency == currency &&
                      (selected == null ||
                          d.date.isEmpty ||
                          d.date == selected),
                ))
                  ListTile(
                    title: Text(
                      d.date.isEmpty
                          ? interpolate(t('analytics.undated'), {
                              'count': d.attempts,
                            })
                          : d.date,
                    ),
                    subtitle: Text(
                      widget.money
                          ? [
                              "${t('analytics.actual')} · ${d.confirmed} $currency",
                              "${t('analytics.estimated')} · ${d.estimated} $currency",
                              if (d.unknownCost > 0)
                                interpolate(t('analytics.unknown_costs'), {
                                  'count': d.unknownCost,
                                }),
                            ].join('\n')
                          : [
                              "${t('analytics.token_input')} ${d.apiInput} · ${t('analytics.token_output')} ${d.apiOutput}",
                              "${t('analytics.api_total')} ${d.apiTokens}",
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
                            ].join('\n'),
                    ),
                  ),
                if (selected != null)
                  TextButton(
                    onPressed: () => setState(() => selected = null),
                    child: Text(t('common.provider_all')),
                  ),
              ],
            ]),
          ),
      ],
    );
  }
}

class _Bars extends StatelessWidget {
  const _Bars({
    required this.t,
    required this.series,
    required this.money,
    required this.selected,
    required this.onSelect,
  });
  final Translate t;
  final List<DayUsage> series;
  final bool money;
  final String? selected;
  final ValueChanged<String> onSelect;

  @override
  Widget build(BuildContext context) {
    if (series.isEmpty) return const SizedBox.shrink();
    // Only plotted coordinates cross into double. All labels and totals retain exact amounts.
    double magnitude(DayUsage d, bool estimate) => money
        ? double.parse((estimate ? d.estimated : d.confirmed).toString())
        : (estimate ? d.estimatedTokens : d.apiTokens).toDouble();
    var max = 0.0;
    for (final d in series) {
      for (final estimate in [false, true]) {
        final h = magnitude(d, estimate);
        if (h > max) max = h;
      }
    }
    double height(DayUsage d, bool estimate) =>
        max > 0 ? (magnitude(d, estimate) / max * 84).clamp(0, 84) : 0;
    final current = series.indexWhere((d) => d.date == selected);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Wrap(
          spacing: 16,
          children: [
            Text(
              t(money ? 'analytics.actual' : 'analytics.api_total'),
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
        SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              for (final d in series)
                Semantics(
                  label: d.date,
                  button: true,
                  selected: d.date == selected,
                  child: InkWell(
                    onTap: () => onSelect(d.date),
                    child: Padding(
                      padding: const EdgeInsets.all(4),
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.end,
                        children: [
                          SizedBox(
                            width: 42,
                            height: 96,
                            child: Stack(
                              alignment: Alignment.bottomCenter,
                              children: [
                                Row(
                                  crossAxisAlignment: CrossAxisAlignment.end,
                                  mainAxisAlignment: MainAxisAlignment.center,
                                  children: [
                                    Container(
                                      width: 12,
                                      height: height(d, false),
                                      color: primary,
                                    ),
                                    const SizedBox(width: 2),
                                    Container(
                                      width: 12,
                                      height: height(d, true),
                                      color: Colors.amber,
                                    ),
                                  ],
                                ),
                                if (money ? d.unknownCost > 0 : d.partial > 0)
                                  const Positioned(
                                    top: 0,
                                    child: Icon(
                                      Icons.circle,
                                      size: 7,
                                      color: muted,
                                    ),
                                  ),
                              ],
                            ),
                          ),
                          Text(
                            d.date.substring(5),
                            style: TextStyle(
                              fontSize: 11,
                              color: d.date == selected ? primary : ink,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
            ],
          ),
        ),
        if (series.length > 1)
          Row(
            children: [
              IconButton(
                tooltip: t('analytics.previous_day'),
                onPressed: current > 0
                    ? () => onSelect(series[current - 1].date)
                    : null,
                icon: const Icon(Icons.chevron_left),
              ),
              Expanded(
                child: Slider(
                  value: (current < 0 ? series.length - 1 : current).toDouble(),
                  max: (series.length - 1).toDouble(),
                  divisions: series.length - 1,
                  semanticFormatterCallback: (v) => series[v.round()].date,
                  onChanged: (v) => onSelect(series[v.round()].date),
                ),
              ),
              IconButton(
                tooltip: t('analytics.next_day'),
                onPressed: current < series.length - 1
                    ? () => onSelect(series[current + 1].date)
                    : null,
                icon: const Icon(Icons.chevron_right),
              ),
            ],
          ),
      ],
    );
  }
}
