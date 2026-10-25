import 'dart:async';

import 'package:flet/flet.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:local_auth/local_auth.dart';
import 'package:local_auth_android/local_auth_android.dart';

// Проверка устройства выдаёт только связанный с попыткой результат.
class TokenlogueRecoveryExtension extends FletExtension {
  @override
  FletService? createService(Control control) {
    if (control.type == 'TokenlogueDeviceRecovery') {
      return TokenlogueRecoveryService(control: control);
    }
    return null;
  }
}

class TokenlogueRecoveryService extends FletService {
  TokenlogueRecoveryService({required super.control});

  final LocalAuthentication _auth = LocalAuthentication();
  final Set<String> _usedAttempts = {};
  String? _activeAttempt;
  Completer<void>? _cancellation;
  bool _disposed = false;

  @override
  void init() {
    super.init();
    control.addInvokeMethodListener(_invokeMethod);
  }

  Map<String, dynamic> _reply(Map args, String status) => {
    'attempt_id': args['attempt_id'],
    'database_id': args['database_id'],
    'epoch': args['epoch'],
    'status': status,
  };

  Future<Map<String, dynamic>> _capabilities() async {
    if (_disposed || defaultTargetPlatform != TargetPlatform.android) {
      return {'api_level': 0, 'recovery_supported': false};
    }
    try {
      final result = await const MethodChannel(
        'io.github.umichata.tokenlogue.native_paths',
      ).invokeMapMethod<String, dynamic>('platformCapabilities');
      return result ?? {'api_level': 0, 'recovery_supported': false};
    } catch (_) {
      return {'api_level': 0, 'recovery_supported': false};
    }
  }

  Future<dynamic> _invokeMethod(String name, dynamic arguments) async {
    final args = arguments is Map ? arguments : <String, dynamic>{};
    final attempt = args['attempt_id'];
    if (name == 'sync_secure_storage') {
      if (_disposed || defaultTargetPlatform != TargetPlatform.android)
        return false;
      try {
        return await const MethodChannel(
              'io.github.umichata.tokenlogue.native_paths',
            ).invokeMethod<bool>('syncSecureStorage') ==
            true;
      } catch (_) {
        return false;
      }
    }
    if (name == 'capabilities') return _capabilities();
    if (name == 'cancel') {
      if (_activeAttempt == attempt) {
        _activeAttempt = null;
        _cancellation?.complete();
        _cancellation = null;
        await _auth.stopAuthentication();
      }
      return true;
    }
    if (name != 'authenticate' || _disposed) {
      return _reply(args, 'error');
    }
    if (defaultTargetPlatform != TargetPlatform.android)
      return _reply(args, 'unavailable');
    if (attempt is! String ||
        attempt.isEmpty ||
        args['database_id'] is! String ||
        args['epoch'] is! int ||
        args['reason'] is! String ||
        args['title'] is! String ||
        args['cancel_label'] is! String) {
      return _reply(args, 'error');
    }
    if (_usedAttempts.contains(attempt)) return _reply(args, 'expired');
    if (_activeAttempt != null) return _reply(args, 'busy');
    _usedAttempts.add(attempt);
    _activeAttempt = attempt;
    final cancellation = Completer<void>();
    _cancellation = cancellation;
    String status;
    try {
      final capabilities = await _capabilities();
      if (_disposed || _activeAttempt != attempt)
        return _reply(args, 'expired');
      final apiLevel = capabilities['api_level'];
      if (apiLevel is! int ||
          apiLevel < 30 ||
          capabilities['recovery_supported'] != true) {
        _activeAttempt = null;
        _cancellation = null;
        return _reply(args, 'unavailable');
      }
      final authentication = _auth.authenticate(
        localizedReason: args['reason'],
        biometricOnly: false,
        persistAcrossBackgrounding: false,
        sensitiveTransaction: true,
        authMessages: [
          AndroidAuthMessages(
            signInTitle: args['title'],
            signInHint: '',
            cancelButton: args['cancel_label'],
          ),
        ],
      );
      // Plugin может отменить callback вместе с окном на старом Android.
      final authenticated = await Future.any<bool>([
        authentication,
        cancellation.future.then((_) => false),
      ]);
      status = authenticated ? 'success' : 'cancelled';
    } on LocalAuthException catch (error) {
      switch (error.code) {
        case LocalAuthExceptionCode.userCanceled:
        case LocalAuthExceptionCode.systemCanceled:
          status = 'cancelled';
        case LocalAuthExceptionCode.timeout:
          status = 'timeout';
        case LocalAuthExceptionCode.noCredentialsSet:
        case LocalAuthExceptionCode.noBiometricHardware:
        case LocalAuthExceptionCode.uiUnavailable:
          status = 'unavailable';
        default:
          status = 'error';
      }
    } catch (_) {
      status = 'error';
    }
    if (_disposed || _activeAttempt != attempt) {
      return _reply(args, 'expired');
    }
    _activeAttempt = null;
    _cancellation = null;
    return _reply(args, status);
  }

  @override
  void dispose() {
    _disposed = true;
    _activeAttempt = null;
    _cancellation?.complete();
    _cancellation = null;
    unawaited(_auth.stopAuthentication());
    control.removeInvokeMethodListener(_invokeMethod);
    super.dispose();
  }
}
