import 'amount.dart';
import 'provider.dart';

/// Do not infer an API total from partial token counters or a currency from an unspecified charge.
class ReportedUsage {
  const ReportedUsage({
    this.input,
    this.output,
    this.total,
    this.cost,
    this.cached,
    this.reasoning,
  });
  final int? input, output, total, cached, reasoning;
  final Amount? cost;
  bool get hasTokens => input != null || output != null || total != null;
  bool get hasAny => hasTokens || cost != null;
  factory ReportedUsage.parse(Object? value, Service service) {
    if (value is! Map) return const ReportedUsage();
    int? count(Object? v) => v is int && v >= 0 ? v : null;
    int? detail(String name, String field) {
      final obj = value[name];
      return obj is Map ? count(obj[field]) : null;
    }

    final price = service == Service.openrouter
        ? Amount.parse(value['cost'])
        : null;
    return ReportedUsage(
      input: count(value['prompt_tokens']),
      output: count(value['completion_tokens']),
      total: count(value['total_tokens']),
      cost: price != null && !price.coefficient.isNegative ? price : null,
      cached: detail('prompt_tokens_details', 'cached_tokens'),
      reasoning: detail('completion_tokens_details', 'reasoning_tokens'),
    );
  }
}

String completionError(Object? error, int status) {
  final raw = error is Map ? error['code'] : null;
  final code = raw is String ? raw.trim().toLowerCase() : raw?.toString();
  const known = {
    'authentication': 'authentication',
    'invalid_request': 'invalid_request',
    'refusal': 'refusal',
    'payment_required': 'payment',
    'insufficient_credits': 'payment',
    'permission_denied': 'permission',
    'content_policy_violation': 'policy',
    'rate_limit_exceeded': 'rate',
    'provider_unavailable': 'unavailable',
    'provider_overloaded': 'overloaded',
    'context_length_exceeded': 'context',
    'max_tokens_exceeded': 'completion',
    'token_limit_exceeded': 'tokens',
    'key_limit_exceeded': 'key_limit',
    'budget_exceeded': 'key_limit',
    'insufficient_quota': 'quota',
    'quota_exceeded': 'quota',
    'daily_quota_exceeded': 'quota',
    'timeout': 'timeout',
  };
  final mapped =
      known[code] ??
      switch (int.tryParse(code ?? '') ?? status) {
        400 => 'invalid_request',
        401 => 'authentication',
        402 => 'payment',
        403 => 'permission',
        408 || 504 => 'timeout',
        429 => 'rate',
        502 || 503 => 'unavailable',
        _ => 'completion',
      };
  return 'service.error.$mapped';
}
