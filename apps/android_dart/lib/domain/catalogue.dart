import 'amount.dart';
import 'provider.dart';

const priceFields = [
  'prompt',
  'completion',
  'request',
  'internal_reasoning',
  'input_cache_read',
  'input_cache_write',
];
const _nonText = {
  'image',
  'audio',
  'input_audio',
  'output_audio',
  'web_search',
};
const _vendors = {
  'openai',
  'anthropic',
  'gryphe',
  'google',
  'amazon',
  'qwen',
  'x-ai',
  'perplexity',
  'mistralai',
  'microsoft',
  'nvidia',
  'meta-llama',
  'nousresearch',
  'sao10k',
  'thedrummer',
  'cohere',
  'deepseek',
  'minimax',
  'moonshotai',
  'z-ai',
  'aion',
  'xiaomi',
};

class ModelChoice {
  ModelChoice(this.service, this.id, this.name, this.context, this.rates);
  final Service service;
  final String id, name;
  final int context;

  /// Each row is the base price or a full conditional pricing override.
  final List<Map<String, Amount>> rates;
  static final router = ModelChoice(
    Service.openrouter,
    'openrouter/free',
    'openrouter/free',
    8192,
    [
      {for (final field in priceFields) field: Amount.zero},
    ],
  );
  bool get free =>
      service == Service.openrouter &&
      rates.isNotEmpty &&
      rates.every((row) => row.values.every((a) => a == Amount.zero));
  Amount? quote(int prompt, int completion) {
    if (rates.isEmpty) return null;
    return rates
        .map(
          (p) =>
              (p['prompt']! + p['input_cache_read']! + p['input_cache_write']!)
                  .times(prompt) +
              (p['completion']! + p['internal_reasoning']!).times(completion) +
              p['request']!,
        )
        .reduce((a, b) => a.compareTo(b) >= 0 ? a : b);
  }

  Amount maximum(String field) => rates
      .map((row) => row[field]!)
      .reduce((a, b) => a.compareTo(b) >= 0 ? a : b);
  Map<String, dynamic> toJson() => {
    'service': service.name,
    'id': id,
    'name': name,
    'context': context,
    'rates': [
      for (final r in rates)
        {for (final e in r.entries) e.key: e.value.toString()},
    ],
  };
  factory ModelChoice.fromJson(Map<String, dynamic> row) => ModelChoice(
    Service.values.byName(row['service'] as String),
    row['id'] as String,
    row['name'] as String,
    row['context'] as int,
    [
      for (final r in row['rates'] as List)
        {for (final k in priceFields) k: Amount.parse(r[k])!},
    ],
  );
  bool exceeds(ModelChoice old) =>
      service != old.service ||
      id != old.id ||
      rates.isEmpty != old.rates.isEmpty ||
      rates.isNotEmpty &&
          priceFields.any((k) => maximum(k).compareTo(old.maximum(k)) > 0);
}

List<ModelChoice> catalogue(Service service, Object? items) {
  if (items is! List) throw const FormatException('catalogue');
  final result = <ModelChoice>[], seen = <String>{};
  for (final row in items.whereType<Map>()) {
    final id = row['id'], name = row['name'];
    final context = int.tryParse('${row['context_length']}');
    if (id is! String ||
        id.trim().isEmpty ||
        name is! String ||
        name.trim().isEmpty ||
        context == null ||
        context < 1) {
      continue;
    }
    if (service == Service.vsegpt) {
      if (_vendors.contains(id.split('/').first.toLowerCase()) &&
          seen.add(id)) {
        result.add(ModelChoice(service, id, name, context, []));
      }
      continue;
    }
    final arch = row['architecture'], price = row['pricing'];
    if (arch is! Map ||
        price is! Map ||
        arch['input_modalities'] is! List ||
        arch['output_modalities'] is! List ||
        !(arch['input_modalities'] as List).contains('text') ||
        !(arch['output_modalities'] as List).contains('text')) {
      continue;
    }
    if (id.startsWith('openrouter/') ||
        id.contains(':') && !id.endsWith(':free') ||
        id
            .toLowerCase()
            .split(RegExp('[/_: -]'))
            .any((s) => s == 'batch' || s == 'online')) {
      continue;
    }
    if (price.keys.any(
      (k) =>
          !priceFields.contains(k) && !_nonText.contains(k) && k != 'overrides',
    )) {
      continue;
    }
    Map<String, Amount>? parse(Map src, Map<String, Amount>? inherited) {
      final p = <String, Amount>{};
      for (final k in priceFields) {
        final amount = src.containsKey(k)
            ? Amount.parse(src[k])
            : inherited?[k] ??
                  (k == 'prompt' || k == 'completion' ? null : Amount.zero);
        if (amount == null || amount.coefficient.isNegative) return null;
        p[k] = amount;
      }
      return p;
    }

    final base = parse(price, null);
    if (base == null) continue;
    final overrides = row['pricing_overrides'] ?? price['overrides'] ?? [];
    if (overrides is! List) continue;
    final rows = [base];
    var complete = true;
    for (final o in overrides) {
      if (o is! Map) {
        complete = false;
        break;
      }
      final raw = o['pricing'] ?? o;
      if (raw is! Map ||
          raw.keys.any(
            (k) =>
                !priceFields.contains(k) &&
                !_nonText.contains(k) &&
                !{
                  'name',
                  'provider',
                  'providers',
                  'quantization',
                  'region',
                  'condition',
                }.contains(k),
          )) {
        complete = false;
        break;
      }
      final p = parse(raw, base);
      if (p == null) {
        complete = false;
        break;
      }
      rows.add(p);
    }
    if (complete && seen.add(id)) {
      result.add(ModelChoice(service, id, name, context, rows));
    }
  }
  return result;
}
