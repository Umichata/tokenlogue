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
                      d.date.isEmpty ? t('analytics.undated') : d.date,
                    ),
                    subtitle: Text(
                      widget.money
                          ? '${t('analytics.actual')}: ${d.confirmed} $currency · ${t('analytics.estimated')}: ${d.estimated} $currency\n${interpolate(t('analytics.day_unknown'), {'count': d.unknownCost})}'
                          : '${t('analytics.api_total')}: ${d.apiTokens} · ≈ ${d.estimatedTokens} · ? ${d.unknownTokens}',
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
    required this.series,
    required this.money,
    required this.selected,
    required this.onSelect,
  });
  final List<DayUsage> series;
  final bool money;
  final String? selected;
  final ValueChanged<String> onSelect;
  @override
  Widget build(BuildContext context) {
    double height(DayUsage d) => money
        ? double.tryParse((d.confirmed + d.estimated).toString()) ?? 0
        : (d.apiTokens + d.estimatedTokens).toDouble();
    final maximum = series.fold<double>(
      0,
      (m, d) => height(d) > m ? height(d) : m,
    );
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          for (final d in series)
            Semantics(
              label: d.date,
              button: true,
              selected: selected == d.date,
              child: InkWell(
                onTap: () => onSelect(d.date),
                child: SizedBox(
                  width: 52,
                  height: 118,
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.end,
                    children: [
                      Container(
                        color: selected == d.date ? Colors.amber : primary,
                        height: maximum > 0
                            ? (height(d) / maximum * 82).clamp(1, 82)
                            : 1,
                        width: 24,
                      ),
                      Text(
                        d.date.substring(5),
                        style: const TextStyle(fontSize: 11),
                      ),
                    ],
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}
