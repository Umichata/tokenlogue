import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:tokenlogue_dart/presentation/analytics_page.dart';
import 'package:tokenlogue_dart/presentation/controls.dart';

void main() {
  for (final locale in ['ru', 'en']) {
    testWidgets(
      'changing width retains the selected analytics filter in $locale',
      (tester) async {
        final words =
            jsonDecode(File('assets/locales/$locale.json').readAsStringSync())
                as Map;
        tester.view.devicePixelRatio = 1;
        tester.view.physicalSize = const Size(400, 900);
        addTearDown(tester.view.reset);
        await tester.pumpWidget(
          MaterialApp(
            home: Scaffold(
              body: AnalyticsPage(
                t: (k) => words[k] as String,
                rows: const [],
                money: true,
              ),
            ),
          ),
        );
        final provider = find.byWidgetPredicate(
          (w) =>
              w is PageFilter<String> && w.label == words['analytics.provider'],
        );
        final period = find.byType(PageFilter<int>);
        Offset position(Finder f) => tester.getTopLeft(f);
        expect(position(period).dy, greaterThan(position(provider).dy));
        final dropdown = find.descendant(
          of: provider,
          matching: find.byType(TextField),
        );
        await tester.tap(dropdown);
        await tester.pumpAndSettle();
        await tester.tap(find.text('VSEGPT').hitTestable().last);
        await tester.pumpAndSettle();
        expect(tester.widget<TextField>(dropdown).controller!.text, 'VSEGPT');
        tester.view.physicalSize = const Size(1150, 720);
        await tester.pumpAndSettle();
        expect(position(provider).dy, position(period).dy);
        expect(position(provider).dx, lessThan(position(period).dx));
        tester.view.physicalSize = const Size(375, 840);
        await tester.pumpAndSettle();
        expect(position(period).dy, greaterThan(position(provider).dy));
        expect(tester.widget<TextField>(dropdown).controller!.text, 'VSEGPT');
        expect(tester.takeException(), isNull);
      },
    );
  }
}
