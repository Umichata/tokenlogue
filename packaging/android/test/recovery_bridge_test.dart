import 'dart:async';

import 'package:flet/flet.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:local_auth_platform_interface/local_auth_platform_interface.dart';

import '../recovery_bridge.dart';

class _Backend extends Fake implements FletBackend {}

class _Authentication extends LocalAuthPlatform {
  final result = Completer<bool>();
  final invoked = Completer<void>();
  int calls = 0;
  int stops = 0;
  AuthenticationOptions? options;

  @override
  Future<bool> authenticate({
    required String localizedReason,
    required Iterable<AuthMessages> authMessages,
    AuthenticationOptions options = const AuthenticationOptions(),
  }) {
    calls += 1;
    this.options = options;
    if (!invoked.isCompleted) invoked.complete();
    return result.future;
  }

  @override
  Future<bool> stopAuthentication() async {
    stops += 1;
    // Намеренно не завершаем callback отменённого платформенного запроса.
    return true;
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const channel = MethodChannel('io.github.umichata.tokenlogue.native_paths');
  const timeout = Duration(seconds: 1);
  final arguments = {
    'attempt_id': 'synthetic-attempt',
    'database_id': 'synthetic-database',
    'epoch': 1,
    'reason': 'Synthetic recovery',
    'title': 'Tokenlogue',
    'cancel_label': 'Cancel',
  };
  late _Authentication authentication;
  late Control control;
  late TokenlogueRecoveryService service;
  late LocalAuthPlatform original;

  setUp(() {
    debugDefaultTargetPlatformOverride = TargetPlatform.android;
    original = LocalAuthPlatform.instance;
    authentication = _Authentication();
    LocalAuthPlatform.instance = authentication;
    control = Control(
      id: 1,
      type: 'TokenlogueDeviceRecovery',
      properties: {},
      backend: _Backend(),
    );
    service = TokenlogueRecoveryService(control: control)..init();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (_) async {
          return {'api_level': 36, 'recovery_supported': true};
        });
  });

  tearDown(() {
    service.dispose();
    LocalAuthPlatform.instance = original;
    debugDefaultTargetPlatformOverride = null;
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, null);
  });

  test('Commit barrier работает независимо от recovery API guard', () async {
    final methods = <String>[];
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
          methods.add(call.method);
          if (call.method == 'syncSecureStorage') return true;
          return {'api_level': 29, 'recovery_supported': false};
        });
    expect(
      await control.invokeMethod('sync_secure_storage', null, timeout),
      true,
    );
    expect(methods, ['syncSecureStorage']);
    expect(authentication.calls, 0);
  });

  test('Отказ commit не превращается в успешное подтверждение', () async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (_) async => false);
    expect(
      await control.invokeMethod('sync_secure_storage', null, timeout),
      false,
    );
    expect(authentication.calls, 0);
  });

  test('API 29 не открывает prompt даже при прямом authenticate', () async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (_) async {
          return {'api_level': 29, 'recovery_supported': true};
        });
    final result = await control.invokeMethod(
      'authenticate',
      arguments,
      timeout,
    );
    expect(result['status'], 'unavailable');
    expect(authentication.calls, 0);
  });

  test('API 30 использует новый challenge с credential fallback', () async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (_) async {
          return {'api_level': 30, 'recovery_supported': true};
        });
    final pending = control.invokeMethod('authenticate', arguments, timeout);
    await authentication.invoked.future.timeout(timeout);
    expect(authentication.options!.biometricOnly, false);
    expect(authentication.options!.stickyAuth, false);
    authentication.result.complete(true);
    expect((await pending)['status'], 'success');
    expect(
      (await control.invokeMethod(
        'authenticate',
        arguments,
        timeout,
      ))['status'],
      'expired',
    );
    expect(authentication.calls, 1);
  });

  test('Ошибка capabilities закрывает доступ без prompt', () async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (_) async {
          throw PlatformException(code: 'fixture_error');
        });
    final result = await control.invokeMethod(
      'authenticate',
      arguments,
      timeout,
    );
    expect(result['status'], 'unavailable');
    expect(authentication.calls, 0);
  });

  test(
    'Отмена во время capabilities не открывает запоздавший prompt',
    () async {
      final entered = Completer<void>();
      final answer = Completer<Map<String, dynamic>>();
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(channel, (_) async {
            entered.complete();
            return answer.future;
          });
      final pending = control.invokeMethod('authenticate', arguments, timeout);
      await entered.future.timeout(timeout);
      await control.invokeMethod('cancel', {
        'attempt_id': arguments['attempt_id'],
      }, timeout);
      answer.complete({'api_level': 36, 'recovery_supported': true});
      expect((await pending.timeout(timeout))['status'], 'expired');
      expect(authentication.calls, 0);
    },
  );

  test('Отмена завершает ожидание даже без native callback', () async {
    final pending = control.invokeMethod('authenticate', arguments, timeout);
    await authentication.invoked.future.timeout(timeout);
    await control.invokeMethod('cancel', {
      'attempt_id': arguments['attempt_id'],
    }, timeout);
    expect((await pending.timeout(timeout))['status'], 'expired');
    authentication.result.complete(true);
    expect(
      (await control.invokeMethod(
        'authenticate',
        arguments,
        timeout,
      ))['status'],
      'expired',
    );
    expect(authentication.calls, 1);
  });
}
