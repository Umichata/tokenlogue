import 'dart:convert';
import 'dart:io';
import 'package:cryptography/cryptography.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:tokenlogue_dart/data/chat_store.dart';
import 'package:tokenlogue_dart/data/journal.dart';
import 'package:tokenlogue_dart/data/providers.dart';
import 'package:tokenlogue_dart/data/session.dart';
import 'package:tokenlogue_dart/data/transport.dart';
import 'package:tokenlogue_dart/data/vault.dart';
import 'package:tokenlogue_dart/domain/catalogue.dart';
import 'package:tokenlogue_dart/domain/provider.dart';
import 'package:tokenlogue_dart/presentation/theme.dart';
import 'package:tokenlogue_dart/presentation/workspace.dart';

class NoAccountTraffic implements Transport {
  @override
  Future<Payload> request(
    Service s,
    String k,
    Resource r, [
    Payload? b,
  ]) async => throw const ApiFailure('catalog.error.network');
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;
  for (final geometry in [
    (420.0, 700.0, 0.0),
    (700.0, 420.0, 140.0),
    (1100.0, 750.0, 0.0),
  ]) {
    testWidgets(
      'a saved conversation remains navigable at ${geometry.$1} by ${geometry.$2} with large text',
      (tester) async {
        late Directory temp;
        late Session session;
        late Map<String, dynamic> words;
        await tester.runAsync(() async {
          temp = await Directory.systemTemp.createTemp('tokenlogue-layout-');
          await databaseFactory.setDatabasesPath(temp.path);
          final profile = UnlockedProfile(
                'test',
                SecretKey(List.filled(32, 4)),
                {},
              ),
              store = await ChatStore.open(profile);
          await store.configure(
            id: 'one',
            title: 'Длинное название заметок для поездки',
            model: ModelChoice.router,
            tokens: 8192,
            output: 32,
            budget: null,
            skip: false,
            reconnect: false,
          );
          await store.saveDraft('one', '  сохранённый черновик 🌱\n', 0);
          session = Session(profile, store, ProviderApi(NoAccountTraffic()));
          words =
              jsonDecode(await File('assets/locales/ru.json').readAsString())
                  as Map<String, dynamic>;
        });
        tester.view.devicePixelRatio = 1;
        tester.view.physicalSize = Size(geometry.$1, geometry.$2);
        tester.view.viewInsets = FakeViewPadding(bottom: geometry.$3);
        addTearDown(tester.view.reset);
        final previousError = FlutterError.onError;
        FlutterError.onError = (details) {
          if (details.informationCollector != null) {
            for (final line in details.informationCollector!()) {
              printOnFailure(line.toStringDeep());
            }
          }
          previousError?.call(details);
        };
        await tester.pumpWidget(
          MaterialApp(
            theme: buildTheme(),
            builder: (ctx, child) => MediaQuery(
              data: MediaQuery.of(
                ctx,
              ).copyWith(textScaler: const TextScaler.linear(1.5)),
              child: child!,
            ),
            home: Workspace(
              session: session,
              api: ProviderApi(NoAccountTraffic()),
              vault: ProfileVault(),
              t: (s) => words[s] as String? ?? s,
              onLock: () {},
              onDelete: () {},
              language: 'ru',
              setLanguage: (_) {},
            ),
          ),
        );
        for (
          var i = 0;
          i < 40 &&
              find
                  .text('Длинное название заметок для поездки')
                  .evaluate()
                  .isEmpty;
          i++
        ) {
          await tester.runAsync(
            () => Future<void>.delayed(const Duration(milliseconds: 20)),
          );
          await tester.pump();
        }
        expect(find.byType(NavigationBar), findsOneWidget);
        expect(find.text('Длинное название заметок для поездки'), findsWidgets);
        FlutterError.onError = previousError;
        expect(tester.takeException(), isNull);
        await tester.pumpWidget(const SizedBox.shrink());
        await tester.runAsync(() async {
          await session.close();
          await temp.delete(recursive: true);
        });
      },
    );
  }
}
