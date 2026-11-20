import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:cryptography/cryptography.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:tokenlogue_dart/data/providers.dart';
import 'package:tokenlogue_dart/data/transport.dart';
import 'package:tokenlogue_dart/data/vault.dart';
import 'package:tokenlogue_dart/domain/amount.dart';
import 'package:tokenlogue_dart/domain/analytics.dart';
import 'package:tokenlogue_dart/domain/provider.dart';
import 'package:tokenlogue_dart/presentation/chat_options.dart';
import 'package:tokenlogue_dart/presentation/provider_page.dart';
import 'package:tokenlogue_dart/presentation/analytics_page.dart';
import 'package:tokenlogue_dart/presentation/theme.dart';

class _AccountReply implements Transport {
  final reply = Completer<Payload>();
  final calls = <Resource>[];
  @override
  Future<Payload> request(
    Service service,
    String key,
    Resource resource, [
    Payload? body,
  ]) {
    expect(service, Service.vsegpt);
    expect(resource, Resource.balance);
    expect(body, isNull);
    calls.add(resource);
    return reply.future;
  }
}

void main() {
  final messages =
      jsonDecode(File('assets/locales/en.json').readAsStringSync())
          as Map<String, dynamic>;
  String t(String key) => messages[key] as String;
  test('calendar days and exact journal facts have distinct scopes', () {
    final now = DateTime(2026, 11, 20, 10);
    final rows = <Attempt>[
      {
        'dispatch_ms': DateTime(2026, 11, 18, 14).millisecondsSinceEpoch,
        'currency': 'RUB',
        'provider': 'vsegpt',
        'requested_model': 'x',
      },
      {
        'dispatch_ms': null,
        'currency': 'USD',
        'provider': 'openrouter',
        'requested_model': 'x',
      },
    ];
    final week = ChartPeriod.forFilter(now, 7, rows);
    expect(week.length, 7);
    expect(week.label(0), '2026-11-14');
    expect(week.label(week.index('2026-11-18')), '2026-11-18');
    expect(week.contains(rows.last), isFalse);
    final all = ChartPeriod.forFilter(now, null, rows);
    expect(all.length, 3);
    final actual = daily(
      rows,
      provider: 'all',
      model: 'all',
      days: 7,
      now: now,
      money: true,
    );
    expect(actual, hasLength(1));
    expect(actual.single.unknownCost, 1);
    expect(actual.single.confirmedCosts, 0);
    expect(actual.single.apiTotalsReported, 0);
  });
  test(
    'display rounding never understates a positive upper bound or rounds away from zero by mistake',
    () {
      final value = Amount.parse('1.23451')!;
      expect(value.forDisplay().toString(), '1.2345');
      expect(value.forDisplay(upperBound: true).toString(), '1.2346');
      expect(Amount.parse('-1.23455')!.forDisplay().toString(), '-1.2346');
      expect(
        Amount.parse('-1.23455')!.forDisplay(upperBound: true).toString(),
        '-1.2345',
      );
      expect(value.toString(), '1.23451');
    },
  );
  testWidgets(
    'chat connection refresh updates authorization in the open menu without a completion',
    (tester) async {
      final transport = _AccountReply();
      final profile = UnlockedProfile('unit', SecretKey(List.filled(32, 4)), {
        'vsegpt': {'key': 'sk-or-vis-menu-fixture', 'verified': false},
      });
      final accounts = AccountState(profile, ProviderApi(transport));
      await tester.pumpWidget(
        MaterialApp(
          theme: buildTheme(),
          home: Scaffold(
            body: ChatOptions(
              t: t,
              language: 'en',
              accounts: accounts,
              service: Service.vsegpt,
              maskedKey: '•••• ture',
              verified: false,
              paid: true,
              skipConfirmation: false,
            ),
          ),
        ),
      );
      expect(find.text('VSEGPT key not verified'), findsOneWidget);
      final refresh = find.widgetWithText(TextButton, t('key.refresh'));
      await tester.ensureVisible(refresh);
      await tester.tap(refresh);
      await tester.pump();
      expect(tester.widget<TextButton>(refresh).onPressed, isNull);
      transport.reply.complete({
        'status': 'ok',
        'data': {'credits': '0', 'subscription_status': 'ok', 'user_status': 0},
      });
      await tester.pumpAndSettle();
      expect(find.text('VSEGPT key accepted'), findsOneWidget);
      expect(transport.calls, [Resource.balance]);
      expect(accounts.values[Service.vsegpt]?.amount, '0');
      expect(find.text('sk-or-vis-menu-fixture'), findsNothing);
      await tester.pumpWidget(const SizedBox.shrink());
      accounts.dispose();
      profile.dispose();
    },
  );
  testWidgets(
    'the token chart permits selecting a day without requests and distinguishes an unknown total',
    (tester) async {
      final now = DateTime.now().toLocal(),
          earlier = DateTime(now.year, now.month, now.day - 2, 12);
      final rows = <Attempt>[
        {
          'id': 'demo',
          'dispatch_ms': earlier.millisecondsSinceEpoch,
          'provider': 'vsegpt',
          'requested_model': 'sample',
          'currency': 'RUB',
        },
      ];
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = const Size(800, 1200);
      addTearDown(tester.view.reset);
      await tester.pumpWidget(
        MaterialApp(
          theme: buildTheme(),
          home: Scaffold(
            body: AnalyticsPage(t: t, rows: rows, money: false),
          ),
        ),
      );
      expect(find.text(dateLabel(earlier)), findsOneWidget);
      expect(
        find.textContaining('API-reported tokens Unavailable'),
        findsWidgets,
      );
      final next = find.byTooltip(t('analytics.next_day'));
      await tester.ensureVisible(next);
      await tester.tap(next);
      await tester.pumpAndSettle();
      expect(find.text(t('analytics.day_no_requests')), findsOneWidget);
      final previous = find.byTooltip(t('analytics.previous_day'));
      await tester.tap(previous);
      await tester.pumpAndSettle();
      expect(find.text(dateLabel(earlier)), findsOneWidget);
    },
  );
}
