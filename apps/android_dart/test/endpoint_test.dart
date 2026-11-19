import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:tokenlogue_dart/data/transport.dart';
import 'package:tokenlogue_dart/domain/provider.dart';

class TestHeaders extends Fake implements HttpHeaders {
  final values = <String, Object>{};
  @override
  void set(String name, Object value, {bool preserveHeaderCase = false}) {
    values[name] = value;
  }

  @override
  set contentType(ContentType? value) {}
}

class TestReply extends Stream<List<int>> implements HttpClientResponse {
  TestReply(this.statusCode, this.payload);
  @override
  final int statusCode;
  final Map<String, dynamic> payload;
  @override
  StreamSubscription<List<int>> listen(
    void Function(List<int>)? onData, {
    Function? onError,
    void Function()? onDone,
    bool? cancelOnError,
  }) => Stream<List<int>>.value(utf8.encode(jsonEncode(payload))).listen(
    onData,
    onError: onError,
    onDone: onDone,
    cancelOnError: cancelOnError,
  );
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class TestRequest extends Fake implements HttpClientRequest {
  TestRequest(this.reply);
  final TestReply reply;
  @override
  final TestHeaders headers = TestHeaders();
  @override
  bool followRedirects = true;
  @override
  bool persistentConnection = true;
  @override
  int contentLength = -1;
  final bytes = <int>[];
  @override
  void add(List<int> data) => bytes.addAll(data);
  @override
  Future<HttpClientResponse> close() async => reply;
}

class TestClient extends Fake implements HttpClient {
  TestClient(this.request);
  final TestRequest request;
  final urls = <Uri>[];
  Object? connectFailure;
  @override
  Duration? connectionTimeout;
  String Function(Uri)? proxy;
  @override
  set findProxy(String Function(Uri)? value) {
    proxy = value;
  }

  @override
  Future<HttpClientRequest> openUrl(String method, Uri uri) async {
    urls.add(uri);
    if (connectFailure != null) throw connectFailure!;
    return request;
  }

  @override
  void close({bool force = false}) {}
}

void main() {
  test(
    'a VSEGPT credential is restricted to its fixed endpoints and the public catalogue omits authorization',
    () async {
      for (final resource in [
        Resource.balance,
        Resource.models,
        Resource.completion,
      ]) {
        final req = TestRequest(TestReply(200, {'data': []})),
            client = TestClient(req);
        await HttpOverrides.runZoned(
          () => HttpsTransport().request(
            Service.vsegpt,
            'sk-or-visLOCAL_TEST',
            resource,
            resource == Resource.completion
                ? {'model': 'unit', 'messages': []}
                : null,
          ),
          createHttpClient: (_) => client,
        );
        expect(client.urls.single.host, 'api.vsegpt.ru');
        expect(client.urls.single.scheme, 'https');
        expect(req.followRedirects, isFalse);
        expect(client.proxy!(client.urls.single), 'DIRECT');
        expect(
          req.headers.values.containsKey(HttpHeaders.authorizationHeader),
          resource != Resource.models,
        );
      }
    },
  );
  test(
    'a redirect never causes another authorized request and a foreign credential opens no connection',
    () async {
      final client = TestClient(TestRequest(TestReply(302, {})));
      await HttpOverrides.runZoned(() async {
        await expectLater(
          HttpsTransport().request(
            Service.openrouter,
            'sk-or-visLOCAL_TEST',
            Resource.key,
          ),
          throwsA(isA<ApiFailure>()),
        );
        expect(client.urls, isEmpty);
        await expectLater(
          HttpsTransport().request(
            Service.openrouter,
            'sk-or-v1-unit',
            Resource.key,
          ),
          throwsA(isA<ApiFailure>()),
        );
        expect(client.urls, hasLength(1));
        expect(client.request.followRedirects, isFalse);
      }, createHttpClient: (_) => client);
    },
  );
  test(
    'failed completion retains reported partial usage and does not automatically repeat',
    () async {
      final client = TestClient(
        TestRequest(
          TestReply(503, {
            'error': {'code': 'provider_overloaded'},
            'usage': {'prompt_tokens': 5, 'cost': '0.0007'},
          }),
        ),
      );
      await HttpOverrides.runZoned(() async {
        await expectLater(
          HttpsTransport().request(
            Service.openrouter,
            'sk-or-v1-unit',
            Resource.completion,
            {'model': 'unit'},
          ),
          throwsA(
            isA<ApiFailure>()
                .having((e) => e.usage.input, 'reported input', 5)
                .having((e) => e.uncertain, 'unknown total', true),
          ),
        );
        expect(client.urls, hasLength(1));
      }, createHttpClient: (_) => client);
    },
  );
  test(
    'TLS and connection timeout reject before transferring a completion',
    () async {
      for (final (exception, label) in [
        (const HandshakeException('synthetic'), 'service.error.tls'),
        (TimeoutException('synthetic'), 'service.error.timeout'),
      ]) {
        final client = TestClient(TestRequest(TestReply(200, {})))
          ..connectFailure = exception;
        await HttpOverrides.runZoned(() async {
          await expectLater(
            HttpsTransport().request(
              Service.vsegpt,
              'sk-or-visLOCAL_TEST',
              Resource.completion,
              {'model': 'unit'},
            ),
            throwsA(
              isA<ApiFailure>()
                  .having((e) => e.label, 'category', label)
                  .having((e) => e.uncertain, 'dispatched', false),
            ),
          );
          expect(client.request.bytes, isEmpty);
          expect(client.urls, hasLength(1));
        }, createHttpClient: (_) => client);
      }
    },
  );
}
