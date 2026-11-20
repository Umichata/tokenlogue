import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import '../domain/amount.dart';
import '../domain/provider.dart';
import '../domain/usage.dart';

typedef Payload = Map<String, dynamic>;

class ApiFailure implements Exception {
  const ApiFailure(
    this.label, {
    this.uncertain = false,
    this.usage = const ReportedUsage(),
  });
  final String label;
  final bool uncertain;
  final ReportedUsage usage;
}

/// Parse non-integral JSON numbers as their original decimal spelling.
Object? decodeProviderJson(String wire) {
  final tokens = RegExp(
    r'"(?:\\.|[^"\\])*"|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?',
  );
  return jsonDecode(
    wire.replaceAllMapped(tokens, (m) {
      final token = m[0]!;
      if (token.startsWith('"') || !token.contains(RegExp('[.eE]'))) {
        return token;
      }
      // Preserve the JSON number type for exact whole counts such as 3.0.
      final number = Amount.parse(token);
      if (number != null &&
          number.scale == 0 &&
          number.coefficient.isValidInt) {
        return number.coefficient.toString();
      }
      return jsonEncode(token);
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
        final bytes = buffer.takeBytes();
        if (response.statusCode == 400 && service == Service.vsegpt) {
          try {
            final raw = jsonDecode(utf8.decode(bytes));
            final msg = raw is Map && raw['error'] is Map
                ? raw['error']['message']
                : null;
            if (msg is String &&
                msg.toLowerCase().contains('api key') &&
                (msg.toLowerCase().contains('not found') ||
                    msg.toLowerCase().contains('original openai'))) {
              throw const ApiFailure('catalog.error.auth');
            }
          } on FormatException {
            /* Keep the HTTP classification for malformed error bodies. */
          }
        }
        if (response.statusCode != 200) {
          if (completion) {
            Object? data;
            try {
              data = decodeProviderJson(utf8.decode(bytes));
            } on FormatException {
              data = null;
            }
            final usage = ReportedUsage.parse(
              data is Map ? data['usage'] : null,
              service,
            );
            final uncertain =
                started &&
                ({408, 500, 502, 503, 504}.contains(response.statusCode) ||
                    usage.hasAny &&
                        (usage.total == null || usage.cost == null));
            throw ApiFailure(
              completionError(
                data is Map ? data['error'] : null,
                response.statusCode,
              ),
              uncertain: uncertain,
              usage: usage,
            );
          }
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
        final object = decodeProviderJson(utf8.decode(bytes));
        if (object is! Payload) {
          throw ApiFailure('catalog.error.schema', uncertain: started);
        }
        return object;
      })().timeout(Duration(seconds: completion ? 100 : 20));
    } on TimeoutException {
      throw ApiFailure(
        completion ? 'service.error.timeout' : 'catalog.error.timeout',
        uncertain: started,
      );
    } on HandshakeException {
      throw ApiFailure(
        completion ? 'service.error.tls' : 'catalog.error.tls',
        uncertain: started,
      );
    } on IOException {
      throw ApiFailure(
        completion ? 'service.error.network' : 'catalog.error.network',
        uncertain: started,
      );
    } on FormatException {
      throw ApiFailure('catalog.error.schema', uncertain: started);
    } finally {
      client.close(force: true);
    }
  }
}
