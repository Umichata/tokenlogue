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
      final response = await transport.request(service, key, Resource.key);
      final data = response['data'];
      if (service == Service.vsegpt && response['status'] != 'ok') {
        final raw = response['error'];
        final message = raw is Map ? raw['message'] : null;
        if (message is String &&
            message.toLowerCase().contains('api key') &&
            (message.toLowerCase().contains('not found') ||
                message.toLowerCase().contains('original openai'))) {
          return KeyStatus.invalid;
        }
        return KeyStatus.unverified;
      }
      if (data is! Map) return KeyStatus.malformed;
      if (service == Service.vsegpt) {
        if (Amount.parse(data['credits']) == null ||
            data['subscription_status'] is! String ||
            ![0, 1, 2].contains(data['user_status'])) {
          return KeyStatus.malformed;
        }
      } else {
        if (!data.containsKey('limit_remaining')) return KeyStatus.malformed;
        if (data['is_management_key'] == true) return KeyStatus.restricted;
        if (data['limit_remaining'] != null &&
            Amount.parse(data['limit_remaining']) == null) {
          return KeyStatus.malformed;
        }
      }
      return KeyStatus.accepted;
    } on ApiFailure catch (e) {
      return switch (e.label) {
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
    }
  }

  Future<({Amount balance, String status})> account(
    Service service,
    String key,
  ) async {
    final result = await transport.request(service, key, Resource.balance);
    final data = result['data'];
    if (service == Service.vsegpt && result['status'] != 'ok') {
      throw const ApiFailure('catalog.error.policy');
    }
    if (data is! Map) throw const ApiFailure('catalog.error.schema');
    if (service == Service.vsegpt) {
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
    final credit = Amount.parse(data['total_credits']),
        usage = Amount.parse(data['total_usage']);
    if (credit == null || usage == null) {
      throw const ApiFailure('catalog.error.schema');
    }
    return (balance: credit - usage, status: 'ready');
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
