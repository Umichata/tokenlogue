import 'amount.dart';

typedef Attempt = Map<String, Object?>;
String dateLabel(DateTime d) =>
    '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';
String modelKey(Attempt a) =>
    '${a['provider']}/${a['actual_model'] ?? a['requested_model']}';

class DayUsage {
  final String date, currency;
  int attempts = 0,
      apiTokens = 0,
      estimatedTokens = 0,
      unknownTokens = 0,
      unknownCost = 0;
  int apiInput = 0,
      apiOutput = 0,
      estimateInput = 0,
      estimateOutput = 0,
      partial = 0;
  Amount confirmed = Amount.zero, estimated = Amount.zero;
  DayUsage(this.date, this.currency);
  void add(Attempt a) {
    attempts++;
    final total = a['usage_total'],
        input = a['usage_in'],
        output = a['usage_out'];
    if (total == null || input == null || output == null) partial++;
    if (a['usage_source'] == 'estimated') {
      estimateInput += input as int? ?? 0;
      estimateOutput += output as int? ?? 0;
    } else if (a['usage_source'] == 'api') {
      apiInput += input as int? ?? 0;
      apiOutput += output as int? ?? 0;
    }
    if (total is! int) {
      unknownTokens++;
    } else if (a['usage_source'] == 'api') {
      apiTokens += total;
    } else {
      estimatedTokens += total;
    }
    final cost = Amount.parse(a['cost']);
    if (cost == null) {
      unknownCost++;
    } else if (a['cost_source'] == 'api') {
      confirmed += cost;
    } else {
      estimated += cost;
    }
  }
}

List<DayUsage> daily(
  List<Attempt> attempts, {
  required String provider,
  required String model,
  required int? days,
  required DateTime now,
  required bool money,
}) {
  final grouped = <String, DayUsage>{};
  final today = now.toLocal(),
      first = days == null
          ? null
          : DateTime(today.year, today.month, today.day - days + 1);
  for (final a in attempts) {
    if (provider != 'all' && a['provider'] != provider ||
        model != 'all' && modelKey(a) != model) {
      continue;
    }
    final stamp = a['dispatch_ms'];
    final d = stamp is int ? DateTime.fromMillisecondsSinceEpoch(stamp) : null;
    if (first != null && (d == null || d.isBefore(first) || d.isAfter(now))) {
      continue;
    }
    final date = d == null ? '' : dateLabel(d),
        currency = money ? a['currency'] as String : '';
    (grouped['$date|$currency'] ??= DayUsage(date, currency)).add(a);
  }
  return grouped.values.toList()..sort((a, b) => a.date.compareTo(b.date));
}
