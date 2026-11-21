import 'package:cryptography/cryptography.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:tokenlogue_dart/data/providers.dart';
import 'package:tokenlogue_dart/data/transport.dart';
import 'package:tokenlogue_dart/data/vault.dart';
import 'package:tokenlogue_dart/domain/catalogue.dart';
import 'package:tokenlogue_dart/domain/provider.dart';
import 'package:tokenlogue_dart/presentation/selection.dart';

class CatalogueFixture extends ProviderApi {
  CatalogueFixture() : super(_UnusedTransport());
  final loaded = <Service>[];
  @override
  Future<List<ModelChoice>> models(Service service, String key) async {
    loaded.add(service);
    ModelChoice model(String id, String name) =>
        ModelChoice(service, id, name, 8192, []);
    return [
      model('test/second', 'Zoo'),
      model('test/C', 'Alpha'),
      model('test/B', 'alpha'),
      if (service == Service.openrouter) ModelChoice.router,
    ];
  }
}

class _UnusedTransport implements Transport {
  @override
  Future<Payload> request(
    Service service,
    String key,
    Resource resource, [
    Payload? body,
  ]) => throw StateError('Unexpected network operation');
}

void main() {
  for (final service in Service.values) {
    testWidgets(
      'catalogue for ${service.label} keeps model identity and back steps',
      (tester) async {
        final api = CatalogueFixture();
        final profile = UnlockedProfile('test', SecretKey(List.filled(32, 1)), {
          'vsegpt': {'key': 'sk-or-vis-local-fixture'},
          'openrouter': {'key': 'sk-or-v1-local-fixture'},
        });
        addTearDown(profile.dispose);
        var repicked = false, cancelled = false;
        tester.view.physicalSize = const Size(960, 1800);
        tester.view.devicePixelRatio = 1;
        addTearDown(tester.view.reset);
        await tester.pumpWidget(
          MaterialApp(
            home: Scaffold(
              body: SelectChat(
                t: (k) => k,
                api: api,
                profile: profile,
                service: service,
                onChooseProvider: () => repicked = true,
                onCancel: () => cancelled = true,
                onSelected: (_) => fail('Browsing must not create a chat'),
              ),
            ),
          ),
        );
        await tester.pumpAndSettle();
        if (service == Service.openrouter) {
          await tester.tap(find.text('mode.choose_free'));
          await tester.pumpAndSettle();
          expect(find.text('model.free_router'), findsOneWidget);
          await tester.binding.handlePopRoute();
          await tester.pumpAndSettle();
          await tester.tap(find.text('mode.choose_paid'));
          await tester.pumpAndSettle();
        }
        final b = tester.getTopLeft(find.text('test/B')).dy;
        expect(b, lessThan(tester.getTopLeft(find.text('test/C')).dy));
        expect(
          tester.getTopLeft(find.text('test/C')).dy,
          lessThan(tester.getTopLeft(find.text('test/second')).dy),
        );
        await tester.enterText(find.byType(TextFormField), 'TEST/B');
        await tester.pumpAndSettle();
        expect(find.text('test/C'), findsNothing);
        await tester.tap(find.text('catalog.select'));
        await tester.pumpAndSettle();
        expect(find.text('limits.configure'), findsOneWidget);
        await tester.binding.handlePopRoute();
        await tester.pumpAndSettle();
        expect(find.text('test/B'), findsOneWidget);
        expect(find.text('test/C'), findsNothing);
        await tester.binding.handlePopRoute();
        await tester.pumpAndSettle();
        if (service == Service.openrouter) {
          expect(find.text('mode.choose_paid'), findsOneWidget);
          await tester.binding.handlePopRoute();
          await tester.pumpAndSettle();
          expect(cancelled, isTrue);
        } else {
          expect(repicked, isTrue);
        }
        expect(api.loaded, [service]);
      },
    );
  }
  for (final service in Service.values) {
    testWidgets(
      'paid limits validate on submit for ${service.label} and deliver one selection',
      (tester) async {
        final profile = UnlockedProfile('unit', SecretKey(List.filled(32, 3)), {
          service.name: {
            'key': service == Service.openrouter
                ? 'sk-or-v1-unit'
                : 'sk-or-vis-unit',
          },
        });
        addTearDown(profile.dispose);
        tester.view.physicalSize = const Size(960, 1800);
        tester.view.devicePixelRatio = 1;
        addTearDown(tester.view.reset);
        final results = <Selection>[];
        await tester.pumpWidget(
          MaterialApp(
            home: Scaffold(
              body: SelectChat(
                t: (k) => k,
                service: service,
                profile: profile,
                api: CatalogueFixture(),
                onCancel: () {},
                onSelected: results.add,
              ),
            ),
          ),
        );
        await tester.pumpAndSettle();
        if (service == Service.openrouter) {
          await tester.tap(find.text('mode.choose_free'));
          await tester.pumpAndSettle();
          await tester.tap(find.text('catalog.select').first);
          await tester.pumpAndSettle();
          expect(find.byType(TextField), findsNWidgets(2));
          expect(find.text('workspace.paid_warning'), findsNothing);
          await tester.tap(find.text('common.back'));
          await tester.pumpAndSettle();
          expect(find.text('model.free_router'), findsOneWidget);
          await tester.tap(find.text('common.back'));
          await tester.pumpAndSettle();
          await tester.tap(find.text('mode.choose_paid'));
          await tester.pumpAndSettle();
        }
        await tester.tap(find.text('catalog.select').first);
        await tester.pumpAndSettle();
        final fields = find.byType(TextField);
        expect(fields, findsNWidgets(3));
        expect(find.byType(Checkbox), findsNothing);
        expect(
          tester.widget<TextField>(fields.at(2)).controller!.text,
          service == Service.openrouter ? '1' : '',
        );
        expect(find.text('workspace.paid_warning'), findsOneWidget);
        expect(find.byType(SelectableText), findsOneWidget);
        await tester.enterText(fields.at(0), '9000');
        await tester.enterText(fields.at(1), '512');
        final button = find.widgetWithText(FilledButton, 'limits.create_paid');
        for (final (raw, message) in [
          ('', 'service.paid_limit_required'),
          ('0', 'service.money_positive'),
          ('-0.01', 'service.money_positive'),
          ('abc', 'service.money_number'),
        ]) {
          await tester.enterText(fields.at(2), raw);
          await tester.tap(button);
          await tester.pump();
          expect(find.text(message), findsOneWidget);
          expect(results, isEmpty);
          expect(
            tester.widget<TextField>(fields.at(0)).controller!.text,
            '9000',
          );
          expect(
            tester.widget<TextField>(fields.at(1)).controller!.text,
            '512',
          );
          expect(tester.widget<TextField>(fields.at(2)).controller!.text, raw);
        }
        await tester.enterText(fields.at(2), '+.01');
        // Both taps reach the same callback before Flutter has redrawn the button.
        final submit = tester.widget<FilledButton>(button).onPressed!;
        submit();
        submit();
        await tester.pump();
        expect(results, hasLength(1));
        expect(results.single.model.service, service);
        expect(results.single.money.toString(), '0.01');
        expect(results.single.tokens, 9000);
        expect(results.single.output, 512);
      },
    );
  }
}
