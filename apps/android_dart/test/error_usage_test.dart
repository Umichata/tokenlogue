import 'package:flutter_test/flutter_test.dart';
import 'package:tokenlogue_dart/domain/usage.dart';
import 'package:tokenlogue_dart/domain/provider.dart';

void main() {
  test(
    'retains partial API usage and refuses to infer totals or VSEGPT currency',
    () {
      final payload = {
        'prompt_tokens': 7,
        'completion_tokens': 5,
        'cost': '0.00000002',
        'prompt_tokens_details': {'cached_tokens': 4},
      };
      final usd = ReportedUsage.parse(payload, Service.openrouter),
          rub = ReportedUsage.parse(payload, Service.vsegpt);
      expect(usd.input, 7);
      expect(usd.output, 5);
      expect(usd.total, isNull);
      expect(usd.cached, 4);
      expect(usd.cost.toString(), '0.00000002');
      expect(rub.hasTokens, isTrue);
      expect(rub.cost, isNull);
    },
  );
  test(
    'quota, authentication and refusal remain distinct from unavailable model and network',
    () {
      expect(
        completionError({'code': 'insufficient_quota'}, 429),
        'service.error.quota',
      );
      expect(
        completionError({'code': 'refusal'}, 200),
        'service.error.refusal',
      );
      expect(completionError(null, 401), 'service.error.authentication');
      expect(completionError(null, 503), 'service.error.unavailable');
    },
  );
}
