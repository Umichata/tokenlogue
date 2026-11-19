import 'dart:async';
import 'dart:convert';
import 'dart:io';

import '../domain/provider.dart';

enum KeyStatus {
  accepted,
  unverified,
  invalid,
  limited,
  unavailable,
  malformed,
}

class ProviderApi {
  Uri _endpoint(Service service, String path) => service == Service.openrouter
      ? Uri.https('openrouter.ai', '/api/v1/$path')
      : Uri.https('api.vsegpt.ru', '/v1/$path');

  Future<({int status, Map<String, dynamic> body})> _read(
    Service service,
    String key,
    String path,
  ) async {
    if (Service.detect(key) != service) {
      throw const FormatException('wrong_provider');
    }
    final client = HttpClient()
      ..connectionTimeout = const Duration(seconds: 10)
      ..findProxy = (_) => 'DIRECT';
    try {
      final req = await client
          .getUrl(_endpoint(service, path))
          .timeout(const Duration(seconds: 12));
      req.followRedirects = false;
      req.headers.set(HttpHeaders.authorizationHeader, 'Bearer ${key.trim()}');
      final resp = await req.close().timeout(const Duration(seconds: 15));
      final bytes = <int>[];
      await for (final chunk in resp.timeout(const Duration(seconds: 15))) {
        if (bytes.length + chunk.length > 10 * 1024 * 1024) {
          throw const FormatException('large_response');
        }
        bytes.addAll(chunk);
      }
      final body = resp.statusCode == 200
          ? jsonDecode(utf8.decode(bytes))
          : <String, dynamic>{};
      if (body is! Map<String, dynamic>) {
        throw const FormatException('response');
      }
      return (status: resp.statusCode, body: body);
    } finally {
      client.close(force: true);
    }
  }

  Future<KeyStatus> check(Service service, String key) async {
    if (Service.detect(key) != service) return KeyStatus.invalid;
    try {
      final response = await _read(
        service,
        key,
        service == Service.openrouter ? 'key' : 'balance',
      );
      if (response.status == 401) return KeyStatus.invalid;
      if (response.status == 403 && service == Service.vsegpt) {
        return KeyStatus.unverified;
      }
      if (response.status == 429) return KeyStatus.limited;
      if (response.status != 200) return KeyStatus.unavailable;
      final data = response.body['data'];
      if (service == Service.vsegpt && response.body['status'] != 'ok') {
        return KeyStatus.unverified;
      }
      if (data is! Map) return KeyStatus.malformed;
      if (service == Service.vsegpt) {
        if (num.tryParse('${data['credits']}')?.isFinite != true ||
            data['subscription_status'] is! String ||
            ![0, 1, 2].contains(data['user_status'])) {
          return KeyStatus.malformed;
        }
      } else if (data['is_management_key'] == true ||
          !data.containsKey('limit_remaining') ||
          (data['limit_remaining'] != null &&
              num.tryParse('${data['limit_remaining']}')?.isFinite != true)) {
        return KeyStatus.invalid;
      }
      return KeyStatus.accepted;
    } on FormatException {
      return KeyStatus.malformed;
    } on IOException {
      return KeyStatus.unavailable;
    } on TimeoutException {
      return KeyStatus.unavailable;
    }
  }
}
