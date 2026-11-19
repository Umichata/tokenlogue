import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:cryptography/cryptography.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:tokenlogue_dart/data/chat_store.dart';
import 'package:tokenlogue_dart/data/vault.dart';
import 'package:tokenlogue_dart/main.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  testWidgets(
    'system approval presents an empty new-PIN form and cancellation or Home leaves the account locked',
    (tester) async {
      sqfliteFfiInit();
      databaseFactory = databaseFactoryFfi;
      late Directory temporary;
      await tester.runAsync(() async {
        temporary = await Directory.systemTemp.createTemp('dart-recovery-ui-');
        await databaseFactory.setDatabasesPath(temporary.path);
        final store = await ChatStore.open(
          UnlockedProfile('widget-test', SecretKey(List.filled(32, 4)), {}),
        );
        await store.db.close();
      });
      final record = {
        'version': 1,
        'id': 'widget-test',
        'dek': base64Encode(List.filled(32, 4)),
        'salt': base64Encode(List.filled(16, 3)),
        'verifier': 'unchanged-unit-verifier',
        'attempts': 0,
        'credentials': <String, dynamic>{},
      };
      var writes = 0;
      late Completer<bool> response;
      final m =
          TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
      m.setMockMethodCallHandler(ProfileVault.channel, (call) async {
        return switch (call.method) {
          'language' => 'en',
          'recoveryAvailable' => true,
          'deleting' => false,
          'read' => Uint8List.fromList(utf8.encode(jsonEncode(record))),
          'authenticateDevice' => response.future,
          'cancelDevice' => null,
          'write' => ++writes,
          _ => null,
        };
      });
      addTearDown(() async {
        m.setMockMethodCallHandler(ProfileVault.channel, null);
        await temporary.delete(recursive: true);
      });
      Future<void> waitFor(String label) async {
        for (var i = 0; i < 80; i++) {
          await tester.pump(const Duration(milliseconds: 20));
          if (find.text(label).evaluate().isNotEmpty) return;
          await tester.runAsync(
            () => Future<void>.delayed(const Duration(milliseconds: 10)),
          );
        }
        fail('Expected public control $label');
      }

      Future<void> tapVisible(String label) async {
        final target = find.text(label);
        await tester.ensureVisible(target);
        await tester.pumpAndSettle();
        for (var i = 0; i < 5 && target.hitTestable().evaluate().isEmpty; i++) {
          await tester.drag(find.byType(ListView).first, const Offset(0, -170));
          await tester.pumpAndSettle();
        }
        expect(target.hitTestable(), findsOneWidget);
        await tester.tap(target.hitTestable());
      }

      await tester.pumpWidget(const Tokenlogue());
      for (final leave in ['cancel', 'flutter', 'host']) {
        response = Completer<bool>();
        await waitFor('Forgot PIN?');
        await tapVisible('Forgot PIN?');
        await waitFor('Confirm on device');
        await tapVisible('Confirm on device');
        await tester.pump();
        response.complete(true);
        await waitFor('Choose a new PIN');
        expect(find.byType(NavigationBar), findsNothing);
        final fields = tester
            .widgetList<TextField>(find.byType(TextField))
            .where((v) => v.obscureText);
        expect(fields.length, 2);
        expect(fields.every((v) => v.controller!.text.isEmpty), isTrue);
        if (leave == 'flutter') {
          tester.binding.handleAppLifecycleStateChanged(
            AppLifecycleState.inactive,
          );
          await tester.pump();
          expect(find.text('Choose a new PIN'), findsOneWidget);
          for (final next in [
            AppLifecycleState.hidden,
            AppLifecycleState.paused,
            AppLifecycleState.hidden,
            AppLifecycleState.inactive,
            AppLifecycleState.resumed,
          ]) {
            tester.binding.handleAppLifecycleStateChanged(next);
            await tester.pump();
          }
        } else if (leave == 'host') {
          bool answered = false;
          Object? generation;
          const codec = StandardMethodCodec();
          final delivered = m.handlePlatformMessage(
            'io.github.umichata.tokenlogue.dart/lifecycle',
            codec.encodeMethodCall(const MethodCall('background', 1)),
            (reply) {
              generation = codec.decodeEnvelope(reply!);
              answered = true;
            },
          );
          await tester.pump();
          await tester.pump();
          await delivered;
          expect(answered, isTrue);
          expect(generation, 1);
        } else {
          await tapVisible('Cancel recovery');
        }
        await waitFor('Forgot PIN?');
        expect(find.byType(NavigationBar), findsNothing);
        expect(writes, 0);
      }
      await tester.pumpWidget(const SizedBox.shrink());
    },
  );
}
