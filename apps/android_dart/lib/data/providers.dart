import '../domain/amount.dart';
import '../domain/catalogue.dart';
import '../domain/provider.dart';
import 'transport.dart';

enum KeyStatus {
  accepted,
  unverified,
  invalid,
  limited,
  unavailable,
  malformed,
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
        return KeyStatus.unverified;
      }
      if (data is! Map) return KeyStatus.malformed;
      if (service == Service.vsegpt) {
        if (Amount.parse(data['credits']) == null ||
            data['subscription_status'] is! String ||
            ![0, 1, 2].contains(data['user_status'])) {
          return KeyStatus.malformed;
        }
      } else if (data['is_management_key'] == true ||
          !data.containsKey('limit_remaining') ||
          data['limit_remaining'] != null &&
              Amount.parse(data['limit_remaining']) == null) {
        return KeyStatus.invalid;
      }
      return KeyStatus.accepted;
    } on ApiFailure catch (e) {
      if (e.label == 'catalog.error.auth') return KeyStatus.invalid;
      if (e.label == 'catalog.error.policy' && service == Service.vsegpt) {
        return KeyStatus.unverified;
      }
      if (e.label == 'catalog.error.rate') return KeyStatus.limited;
      return KeyStatus.unavailable;
    }
  }

  Future<({Amount balance, Amount? limit, bool limitKnown})> account(
    Service service,
    String key,
  ) async {
    final result = await transport.request(service, key, Resource.balance);
    final data = result['data'];
    if (data is! Map) throw const ApiFailure('catalog.error.schema');
    if (service == Service.vsegpt) {
      if (result['status'] != 'ok') {
        throw const ApiFailure('catalog.error.policy');
      }
      final balance = Amount.parse(data['credits']);
      if (balance == null) throw const ApiFailure('catalog.error.schema');
      return (balance: balance, limit: null, limitKnown: false);
    }
    final credit = Amount.parse(data['total_credits']),
        usage = Amount.parse(data['total_usage']);
    if (credit == null || usage == null) {
      throw const ApiFailure('catalog.error.schema');
    }
    final balance = credit - usage;
    try {
      final info = (await transport.request(
        service,
        key,
        Resource.key,
      ))['data'];
      if (info is Map && info.containsKey('limit_remaining')) {
        final limit = Amount.parse(info['limit_remaining']);
        return (
          balance: balance,
          limit: limit,
          limitKnown: limit != null || info['limit_remaining'] == null,
        );
      }
    } on ApiFailure {
      /* Credits and key limit are independent observations. */
    }
    return (balance: balance, limit: null, limitKnown: false);
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
