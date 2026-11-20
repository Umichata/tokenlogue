import '../domain/amount.dart';
import '../domain/catalogue.dart';
import '../domain/provider.dart';
import 'transport.dart';

enum KeyStatus {
  accepted('providers.checked'),
  unverified('selection.key.vsegpt_balance_unavailable'),
  invalid('service.auth_rejected'),
  restricted('service.auth_restricted'),
  limited('service.auth_rate'),
  network('service.auth_network'),
  timeout('service.auth_timeout'),
  tls('service.auth_tls'),
  unavailable('service.auth_unavailable'),
  malformed('service.response_format');

  const KeyStatus(this.message);
  final String message;

  static KeyStatus fromFailure(Service service, ApiFailure failure) =>
      switch (failure.label) {
        'catalog.error.auth' => KeyStatus.invalid,
        'catalog.error.policy' =>
          service == Service.vsegpt
              ? KeyStatus.unverified
              : KeyStatus.restricted,
        'catalog.error.schema' => KeyStatus.malformed,
        'catalog.error.rate' => KeyStatus.limited,
        'catalog.error.timeout' => KeyStatus.timeout,
        'catalog.error.tls' => KeyStatus.tls,
        'catalog.error.network' => KeyStatus.network,
        _ => KeyStatus.unavailable,
      };

  bool maySaveUnverified(Service service) =>
      service == Service.vsegpt &&
      switch (this) {
        unverified ||
        limited ||
        network ||
        timeout ||
        tls ||
        unavailable => true,
        _ => false,
      };
}

typedef DailyQuota = ({int remaining, int limit});
typedef RouterKeyLimits = ({Amount? amount, DailyQuota? daily});

DailyQuota? _dailyQuota(Object? raw) {
  if (raw is! Map) return null;
  final used = raw['used'], limit = raw['limit'], remaining = raw['remaining'];
  if (used is! int ||
      limit is! int ||
      remaining is! int ||
      used < 0 ||
      limit < 0 ||
      remaining != (used >= limit ? 0 : limit - used)) {
    return null;
  }
  return (remaining: remaining, limit: limit);
}

class ProviderApi {
  ProviderApi([Transport? transport])
    : transport = transport ?? HttpsTransport();
  final Transport transport;
  Future<KeyStatus> check(Service service, String key) async {
    if (Service.detect(key) != service) return KeyStatus.invalid;
    try {
      if (service == Service.openrouter) {
        await routerKeyLimits(key);
      } else {
        _readVsegptAccount(await transport.request(service, key, Resource.key));
      }
      return KeyStatus.accepted;
    } on ApiFailure catch (e) {
      return KeyStatus.fromFailure(service, e);
    }
  }

  Future<({Amount balance, String status})> account(
    Service service,
    String key,
  ) async {
    final result = await transport.request(service, key, Resource.balance);
    if (service == Service.vsegpt) return _readVsegptAccount(result);
    final data = result['data'];
    if (data is! Map) throw const ApiFailure('catalog.error.schema');
    final credit = Amount.parse(data['total_credits']),
        usage = Amount.parse(data['total_usage']);
    if (credit == null || usage == null) {
      throw const ApiFailure('catalog.error.schema');
    }
    return (balance: credit - usage, status: 'ready');
  }

  ({Amount balance, String status}) _readVsegptAccount(Payload result) {
    if (result['status'] != 'ok') {
      final error = result['error'];
      final message = error is Map ? error['message'] : null;
      if (message is String &&
          message.toLowerCase().contains('api key') &&
          (message.toLowerCase().contains('not found') ||
              message.toLowerCase().contains('original openai'))) {
        throw const ApiFailure('catalog.error.auth');
      }
      throw const ApiFailure('catalog.error.policy');
    }
    final data = result['data'];
    if (data is! Map) throw const ApiFailure('catalog.error.schema');
    final balance = Amount.parse(data['credits']);
    if (balance == null) throw const ApiFailure('catalog.error.schema');
    final subscription = data['subscription_status'],
        account = data['user_status'];
    if (subscription is! String || ![0, 1, 2].contains(account)) {
      throw const ApiFailure('catalog.error.schema');
    }
    final status = subscription != 'ok'
        ? 'subscription_required'
        : account == 2
        ? (balance.compareTo(Amount.zero) <= 0
              ? 'insufficient_funds'
              : 'account_disabled')
        : account == 1
        ? 'warning'
        : 'ready';
    return (balance: balance, status: status);
  }

  Future<RouterKeyLimits> routerKeyLimits(String key) async {
    final info = (await transport.request(
      Service.openrouter,
      key,
      Resource.key,
    ))['data'];
    if (info is! Map || !info.containsKey('limit_remaining')) {
      throw const ApiFailure('catalog.error.schema');
    }
    if (info['is_management_key'] == true) {
      throw const ApiFailure('catalog.error.policy');
    }
    final amount = Amount.parse(info['limit_remaining']);
    if (info['limit_remaining'] != null && amount == null) {
      throw const ApiFailure('catalog.error.schema');
    }
    return (
      amount: amount,
      daily: _dailyQuota(info['free_model_daily_requests']),
    );
  }

  Future<List<ModelChoice>> models(Service service, String key) async {
    final data = await transport.request(service, key, Resource.models);
    try {
      return catalogue(service, data['data']);
    } on FormatException {
      throw const ApiFailure('catalog.error.schema');
    }
  }
}
