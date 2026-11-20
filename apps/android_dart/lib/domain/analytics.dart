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
  int apiRequests = 0, unknownRequests = 0;
  int apiInputsReported = 0, apiOutputsReported = 0, apiTotalsReported = 0;
  int confirmedCosts = 0, estimatedCosts = 0;
  Amount confirmed = Amount.zero, estimated = Amount.zero;
  DayUsage(this.date, this.currency);
  void add(Attempt a) {
    attempts++;
    final total = a['usage_total'],
        input = a['usage_in'],
        output = a['usage_out'];
    if (total == null || input == null || output == null) partial++;
    if (a['usage_source'] == 'api' &&
        (total is int || input is int || output is int)) {
      apiRequests++;
    } else if (a['usage_source'] != 'estimated' ||
        (total == null && input == null && output == null)) {
      unknownRequests++;
    }
    if (a['usage_source'] == 'estimated') {
      estimateInput += input as int? ?? 0;
      estimateOutput += output as int? ?? 0;
    } else if (a['usage_source'] == 'api') {
      if (input is int) apiInputsReported++;
      if (output is int) apiOutputsReported++;
      apiInput += input as int? ?? 0;
      apiOutput += output as int? ?? 0;
    }
    if (total is! int) {
      unknownTokens++;
    } else if (a['usage_source'] == 'api') {
      apiTotalsReported++;
      apiTokens += total;
    } else {
      estimatedTokens += total;
    }
    final cost = Amount.parse(a['cost']);
    if (cost == null) {
      unknownCost++;
    } else if (a['cost_source'] == 'api') {
      confirmedCosts++;
      confirmed += cost;
    } else {
      estimatedCosts++;
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
  final period = days == null
      ? null
      : ChartPeriod.forFilter(now, days, const []);
  for (final a in attempts) {
    if (provider != 'all' && a['provider'] != provider ||
        model != 'all' && modelKey(a) != model) {
      continue;
    }
    final stamp = a['dispatch_ms'];
    final d = stamp is int ? DateTime.fromMillisecondsSinceEpoch(stamp) : null;
    if (period != null && !period.contains(a)) continue;
    final date = d == null ? '' : dateLabel(d),
        currency = money ? a['currency'] as String : '';
    (grouped['$date|$currency'] ??= DayUsage(date, currency)).add(a);
  }
  return grouped.values.toList()..sort((a, b) => a.date.compareTo(b.date));
}

/// The chart includes calendar days without dispatches. The journal remains sparse.
class ChartPeriod {
  ChartPeriod._(this.start, this.end);
  final DateTime start, end;

  static DateTime _day(DateTime local) =>
      DateTime.utc(local.year, local.month, local.day);

  factory ChartPeriod.forFilter(
    DateTime now,
    int? days,
    Iterable<Attempt> rows,
  ) {
    var end = _day(now.toLocal()), start = end;
    if (days != null) {
      start = end.subtract(Duration(days: days - 1));
    } else {
      DateTime? earliest;
      for (final row in rows) {
        if (row['dispatch_ms'] case final int stamp) {
          final date = _day(DateTime.fromMillisecondsSinceEpoch(stamp));
          if (earliest == null || date.isBefore(earliest)) earliest = date;
          if (date.isAfter(end)) end = date;
        }
      }
      start = earliest ?? end;
    }
    return ChartPeriod._(start, end);
  }
  int get length => end.difference(start).inDays + 1;
  String label(int i) => dateLabel(start.add(Duration(days: i)));
  int index(String label) {
    final date = DateTime.tryParse('${label}T00:00:00Z');
    return date == null ? -1 : date.difference(start).inDays;
  }

  bool contains(Attempt row) {
    final stamp = row['dispatch_ms'];
    if (stamp is! int) return false;
    final day = _day(DateTime.fromMillisecondsSinceEpoch(stamp));
    return !day.isBefore(start) && !day.isAfter(end);
  }
}
