import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:tokenlogue_dart/main.dart' as app;

import 'history_scenario.dart';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  testWidgets(
    'fresh isolated Android installation renders the key form and identifies both VSEGPT key prefixes locally',
    (tester) async {
      app.main();
      for (
        var i = 0;
        i < 50 && find.byType(TextField).evaluate().length < 2;
        i++
      ) {
        await tester.pump(const Duration(milliseconds: 100));
      }
      final input = find.byWidgetPredicate(
        (w) => w is TextField && w.obscureText,
      );
      expect(input, findsOneWidget);
      for (final fixture in ['sk-or-visLOCAL_TEST', 'sk-or-vv-local-fixture']) {
        await tester.enterText(input, fixture);
        await tester.pumpAndSettle();
        expect(find.textContaining('VSEGPT'), findsWidgets);
        expect(
          tester
              .widget<FilledButton>(
                find.byWidgetPredicate((w) => w is FilledButton),
              )
              .onPressed,
          isNotNull,
        );
      }
      await tester.enterText(input, 'sk-or-vis-');
      await tester.pumpAndSettle();
      expect(
        tester
            .widget<FilledButton>(
              find.byWidgetPredicate((w) => w is FilledButton),
            )
            .onPressed,
        isNull,
      );
    },
  );
  registerHistoryScenario();
}
