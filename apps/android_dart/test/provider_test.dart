import 'package:flutter_test/flutter_test.dart';
import 'package:tokenlogue_dart/domain/provider.dart';

void main() {
  test('only supported service-specific prefixes with a printable suffix', () {
    for (final k in [
      'sk-or-visLOCAL_TEST',
      'sk-or-vis-local-fixture',
      'sk-or-vv-unit',
    ]) {
      expect(Service.detect(' $k '), Service.vsegpt);
    }
    expect(Service.detect('sk-or-v1-unit'), Service.openrouter);
    for (final k in [
      '',
      'sk-or-v1-',
      'sk-or-vv-',
      'sk-or-vis',
      'sk-or-vis-',
      'sk-or-other',
      'sk-or-vis🚫',
      'sk-or-visA B',
      'sk-or-visA\x00B',
    ]) {
      expect(Service.detect(k), isNull);
    }
  });
}
