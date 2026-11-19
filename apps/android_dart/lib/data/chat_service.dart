import 'dart:convert';
import '../domain/amount.dart';
import '../domain/catalogue.dart';
import '../domain/provider.dart';
import '../domain/request_plan.dart';
import 'chat_store.dart';
import 'journal.dart';
import 'providers.dart';
import 'transport.dart';

class ChangedPrice implements Exception {
  ChangedPrice(this.chat, this.version, this.current);
  final String chat;
  final int version;
  final ModelChoice current;
}

class PreparedSend {
  PreparedSend(
    this.chat,
    this.version,
    this.rev,
    this.text,
    this.model,
    this.plan,
    this.rows,
    this.skip,
    this.retry,
  );
  final String chat, text;
  final int version, rev;
  final ModelChoice model;
  final RequestPlan plan;
  final List<JournalRow> rows;
  final bool skip;
  final String? retry;
}

class ChatService {
  ChatService(this.store, this.api);
  final ChatStore store;
  final ProviderApi api;
  bool closed = false;
  int _generation = 0;
  final _busy = <String>{};
  final Map<PreparedSend, String> _authorizations = {};
  void invalidate() {
    _generation++;
    _authorizations.clear();
  }

  String _key(Service s) {
    final value = store.crypto.profile.keyFor(s);
    if (closed || value == null || Service.detect(value) != s) {
      throw const PlanRejected('service.error.key_state');
    }
    return value;
  }

  Future<PreparedSend> preview(ChatRecord chat, {String? retry}) async {
    if (closed || _busy.contains(chat.id)) {
      throw const PlanRejected('service.error.turn_active');
    }
    final generation = _generation;
    final rows = await store.journal(chat: chat.id);
    final total = totals(rows, chat.service);
    if (total.blocked) {
      throw const PlanRejected('service.previous_unknown');
    }
    final settings = await store.settings(chat.id);
    final history = await store.history(chat.id);
    var text = chat.draft.trim();
    List<Map<String, String>>? previousContext;
    if (retry != null) {
      final last = rows.where((a) => a['turn_id'] == retry).lastOrNull;
      if (last == null ||
          last['state'] != 'failed' ||
          last['provider'] != chat.service.name ||
          last['requested_model'] != chat.model) {
        throw const PlanRejected('service.error.retry');
      }
      previousContext = await store.dispatchSnapshot(last);
      text = history
          .firstWhere((m) => m.turn == retry && m.role == 'user')
          .body;
    }
    final key = _key(chat.service);
    final model =
        chat.model == ModelChoice.router.id &&
            chat.free &&
            chat.service == Service.openrouter
        ? ModelChoice.router
        : (await api.models(
            chat.service,
            key,
          )).where((m) => m.id == chat.model).firstOrNull;
    if (generation != _generation || key != _key(chat.service)) {
      throw const PlanRejected('service.error.key_state');
    }
    if (model == null) throw const PlanRejected('service.error.model_missing');
    if (model.free != chat.free) {
      throw const PlanRejected('service.error.price_unsafe');
    }
    final old = settings['price'] as String?;
    if (old != null &&
        model.exceeds(ModelChoice.fromJson(jsonDecode(old) as Payload))) {
      throw ChangedPrice(chat.id, settings['connection_rev'] as int, model);
    }
    final pairs = <ChatPair>[];
    for (final u in history.where((m) => m.role == 'user')) {
      final a = history
          .where((m) => m.role == 'assistant' && m.turn == u.turn)
          .firstOrNull;
      if (a != null) pairs.add((user: u.body, assistant: a.body));
    }
    if (previousContext != null) {
      if (previousContext.isEmpty ||
          previousContext.last['role'] != 'user' ||
          previousContext.last['content'] != text ||
          previousContext.length.isEven) {
        throw const PlanRejected('service.error.retry');
      }
      pairs.clear();
      for (var i = 0; i < previousContext.length - 1; i += 2) {
        final user = previousContext[i], answer = previousContext[i + 1];
        if (user['role'] != 'user' || answer['role'] != 'assistant') {
          throw const PlanRejected('service.error.retry');
        }
        pairs.add((user: user['content']!, assistant: answer['content']!));
      }
    }
    final balance = await store.limitFor(chat.id, chat.service);
    Amount? remaining;
    if (!chat.free && chat.service == Service.openrouter) {
      final metadata = (await api.transport.request(
        chat.service,
        key,
        Resource.key,
      ))['data'];
      if (metadata is! Map ||
          !metadata.containsKey('limit_remaining') ||
          metadata['is_management_key'] == true) {
        throw const PlanRejected('service.error.key_state');
      }
      if (metadata['limit_remaining'] != null) {
        remaining = Amount.parse(metadata['limit_remaining']);
        if (remaining == null) {
          throw const PlanRejected('service.error.key_state');
        }
      }
    }
    final plan = RequestPlan.prepare(
      model: model,
      text: text,
      history: pairs,
      availableTokens:
          (settings['token_limit'] as int? ?? 8192) -
          total.used -
          total.reserved,
      outputLimit: settings['response_limit'] as int,
      budget: balance,
      spent: total.spent,
      reserved: total.held,
      keyRemaining: remaining,
    );
    if (generation != _generation || key != _key(chat.service)) {
      throw const PlanRejected('service.error.key_state');
    }
    if (previousContext != null &&
        jsonEncode(previousContext) != jsonEncode(plan.messages)) {
      throw const PlanRejected('service.error.context');
    }
    final send = PreparedSend(
      chat.id,
      settings['connection_rev'] as int,
      chat.revision,
      text,
      model,
      plan,
      rows,
      settings['skip_paid'] == 1,
      retry,
    );
    _authorizations[send] = key;
    return send;
  }

  Future<void> dispatch(PreparedSend send, {required bool confirmed}) async {
    final key = _authorizations.remove(send),
        model = send.model,
        plan = send.plan;
    if (key == null || key != _key(model.service)) {
      throw const PlanRejected('service.error.key_state');
    }
    if (!model.free &&
        (!send.skip || plan.warning || model.rates.isEmpty) &&
        !confirmed) {
      throw const PlanRejected('service.error.paid_confirm');
    }
    if (!model.free) {
      final current = (await store.chats())
          .where((c) => c.id == send.chat)
          .firstOrNull;
      if (current == null) throw const PlanRejected('connection.stale');
      final refreshed = await preview(current, retry: send.retry);
      final currentKey = _authorizations.remove(refreshed);
      if (currentKey != key ||
          refreshed.version != send.version ||
          refreshed.rev != send.rev ||
          refreshed.plan.prompt != plan.prompt ||
          refreshed.plan.completion != plan.completion ||
          refreshed.plan.reservationAmount != plan.reservationAmount ||
          refreshed.plan.projected != plan.projected ||
          refreshed.plan.warning != plan.warning ||
          refreshed.skip != send.skip ||
          jsonEncode(refreshed.model.toJson()) != jsonEncode(model.toJson()) ||
          jsonEncode(refreshed.plan.messages) != jsonEncode(plan.messages)) {
        throw const PlanRejected('paid.confirm_required');
      }
    }
    if (!_busy.add(send.chat)) {
      throw const PlanRejected('service.error.turn_active');
    }
    try {
      final ids = await store.reserve(
        chat: send.chat,
        text: send.text,
        rev: send.rev,
        connection: send.version,
        model: model,
        plan: plan,
        observed: send.rows,
        retryTurn: send.retry,
      );
      try {
        if (closed || key != _key(model.service)) {
          throw const ApiFailure('service.error.key_state');
        }
        final payload = <String, dynamic>{
          'model': model.id,
          'messages': plan.messages,
          'stream': false,
          if (model.service == Service.vsegpt)
            'max_tokens': plan.completion
          else ...{
            'max_completion_tokens': plan.completion,
            'provider': {
              'allow_fallbacks': true,
              'max_price': {
                'prompt': model.maximum('prompt').times(1000000),
                'completion': model.maximum('completion').times(1000000),
                'request': model.maximum('request'),
              },
            },
          },
        };
        final result = await api.transport.request(
          model.service,
          key,
          Resource.completion,
          payload,
        );
        final choices = result['choices'];
        final actual = result['model'];
        if (result['error'] != null ||
            actual is! String ||
            actual.isEmpty ||
            choices is! List ||
            choices.isEmpty ||
            choices.first is! Map) {
          throw const ApiFailure('service.error.completion', uncertain: true);
        }
        final choice = choices.first as Map;
        final message = choice['message'];
        if (choice['error'] != null ||
            !['stop', 'length'].contains(choice['finish_reason']) ||
            message is! Map ||
            message['content'] is! String ||
            message['role'] != 'assistant') {
          throw const ApiFailure('service.error.completion', uncertain: true);
        }
        final usage = result['usage'];
        int? count(String k) {
          final v = usage is Map ? usage[k] : null;
          return v is int && v >= 0 ? v : null;
        }

        final cost = model.service == Service.openrouter && usage is Map
            ? Amount.parse(usage['cost'])
            : null;
        final safeCost = cost != null && !cost.coefficient.isNegative
            ? cost
            : null;
        await store.settle(
          chat: send.chat,
          turn: ids.turn,
          attempt: ids.attempt,
          answer: message['content'] as String,
          actual: actual,
          input: count('prompt_tokens'),
          output: count('completion_tokens'),
          total: count('total_tokens'),
          cost: safeCost,
          costSource: safeCost == null ? 'unknown' : 'api',
          usageSource: count('total_tokens') == null ? 'unknown' : 'api',
          unknown: count('total_tokens') == null || safeCost == null,
        );
      } on ApiFailure catch (e) {
        await store.fail(ids.attempt, e.label, e.uncertain);
        rethrow;
      }
    } finally {
      _busy.remove(send.chat);
    }
  }
}
