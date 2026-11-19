import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:tokenlogue_dart/presentation/message_body.dart';
import 'package:tokenlogue_dart/presentation/theme.dart';

void main() {
  testWidgets(
    'a formatted untrusted message does not create image fetches, clickable links or embedded HTML',
    (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: buildTheme(),
          home: const Scaffold(
            body: MessageBody(
              source:
                  '# Plan\n\n> Keep this locally.\n\n1. **Review**\n\n![external](https://example.invalid/track)\n\n[remote](file:///example)\n\n```dart\nvar result = 4;\n```',
              copyLabel: 'Copy code',
            ),
          ),
        ),
      );
      expect(find.byType(Image), findsNothing);
      expect(find.byTooltip('Copy code'), findsOneWidget);
      expect(find.byType(SelectableText), findsWidgets);
      expect(tester.takeException(), isNull);
    },
  );
}
