import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import '../domain/amount.dart';
import '../domain/provider.dart';

typedef Payload = Map<String, dynamic>;

class ApiFailure implements Exception {
  const ApiFailure(this.label, {this.uncertain = false});
  final String label;
  final bool uncertain;
}

/// Parse non-integral JSON numbers as their original decimal spelling.
Object? decodeProviderJson(String wire) {
  final tokens = RegExp(
    r'"(?:\\.|[^"\\])*"|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?',
  );
  return jsonDecode(
    wire.replaceAllMapped(tokens, (m) {
      final token = m[0]!;
      return token.startsWith('"') || !token.contains(RegExp('[.eE]'))
          ? token
          : jsonEncode(token);
    }),
  );
}

/// Emit provider routing prices as JSON numbers without passing through double.
String encodePayload(Object? value) {
  if (value is Amount) return value.toString();
  if (value is List) return '[${value.map(encodePayload).join(',')}]';
  if (value is Map) {
    return '{${value.entries.map((e) => '${jsonEncode(e.key)}:${encodePayload(e.value)}').join(',')}}';
  }
  return jsonEncode(value);
}

enum Resource { key, balance, models, completion }

abstract interface class Transport {
  Future<Payload> request(
    Service service,
    String key,
    Resource resource, [
    Payload? body,
  ]);
}

class HttpsTransport implements Transport {
  @override
  Future<Payload> request(
    Service service,
    String key,
    Resource resource, [
    Payload? body,
  ]) async {
    if (Service.detect(key) != service) {
      throw const ApiFailure('catalog.error.key_mismatch');
    }
    final completion = resource == Resource.completion;
    if (completion != (body != null)) throw ArgumentError('method');
    final path = switch (resource) {
      Resource.key => service == Service.vsegpt ? 'balance' : 'key',
      Resource.balance => service == Service.vsegpt ? 'balance' : 'credits',
      Resource.models => 'models',
      Resource.completion => 'chat/completions',
    };
    final uri = service == Service.openrouter
        ? Uri.https('openrouter.ai', '/api/v1/$path')
        : Uri.https('api.vsegpt.ru', '/v1/$path');
    final client = HttpClient()
      ..connectionTimeout = const Duration(seconds: 10)
      ..findProxy = (_) => 'DIRECT';
    var started = false;
    try {
      return await (() async {
        final request = await client.openUrl(completion ? 'POST' : 'GET', uri);
        request.followRedirects = false;
        request.persistentConnection = false;
        if (service != Service.vsegpt || resource != Resource.models) {
          request.headers.set(
            HttpHeaders.authorizationHeader,
            'Bearer ${key.trim()}',
          );
        }
        if (body != null) {
          final bytes = utf8.encode(encodePayload(body));
          request.headers.contentType = ContentType.json;
          request.contentLength = bytes.length;
          started = true;
          request.add(bytes);
        }
        final response = await request.close();
        final buffer = BytesBuilder(copy: false);
        await for (final chunk in response) {
          if (buffer.length + chunk.length > 12 * 1024 * 1024) {
            throw ApiFailure('catalog.error.schema', uncertain: started);
          }
          buffer.add(chunk);
        }
        if (response.statusCode != 200) {
          final label = switch (response.statusCode) {
            401 => 'catalog.error.auth',
            402 => 'catalog.error.balance',
            403 => 'catalog.error.policy',
            429 => 'catalog.error.rate',
            _ => 'catalog.error.http',
          };
          throw ApiFailure(
            label,
            uncertain: started && response.statusCode >= 500,
          );
        }
        final object = decodeProviderJson(utf8.decode(buffer.takeBytes()));
        if (object is! Payload) {
          throw ApiFailure('catalog.error.schema', uncertain: started);
        }
        return object;
      })().timeout(Duration(seconds: completion ? 100 : 20));
    } on TimeoutException {
      throw ApiFailure('catalog.error.timeout', uncertain: started);
    } on HandshakeException {
      throw ApiFailure('catalog.error.tls', uncertain: started);
    } on IOException {
      throw ApiFailure('catalog.error.network', uncertain: started);
    } on FormatException {
      throw ApiFailure('catalog.error.schema', uncertain: started);
    } finally {
      client.close(force: true);
    }
  }
}
