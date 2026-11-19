import 'dart:convert';
import 'amount.dart';
import 'catalogue.dart';

typedef ChatPair = ({String user, String assistant});

class PlanRejected implements Exception {
  const PlanRejected(this.message);
  final String message;
}

int estimateText(String value) => utf8.encode(value).length + 8;

class RequestPlan {
  RequestPlan(
    this.messages,
    this.prompt,
    this.completion,
    this.reserve,
    this.warning,
    this.projected,
  );
  final List<Map<String, String>> messages;
  final int prompt, completion;
  final Amount? reserve, projected;
  final bool warning;

  factory RequestPlan.prepare({
    required ModelChoice model,
    required String text,
    required List<ChatPair> history,
    required int availableTokens,
    required int outputLimit,
    required Amount? budget,
    required Amount spent,
    required Amount reserved,
    required Amount? keyRemaining,
  }) {
    if (text.trim().isEmpty) throw const PlanRejected('estimate.empty');
    var output = outputLimit.clamp(
      0,
      availableTokens < 0 ? 0 : availableTokens,
    );
    if (output < 16) throw const PlanRejected('service.error.tokens');
    var prompt = 32 + estimateText(text);
    if (prompt + 16 > model.context) {
      throw const PlanRejected('service.error.context');
    }
    if (prompt + 16 > availableTokens) {
      throw const PlanRejected('service.error.tokens');
    }
    output = output.clamp(
      16,
      (availableTokens - prompt).clamp(16, model.context - prompt),
    );
    final pairs = <ChatPair>[];
    for (final pair in history.reversed) {
      final cost = estimateText(pair.user) + estimateText(pair.assistant);
      if (prompt + cost + output > model.context ||
          prompt + cost + output > availableTokens) {
        break;
      }
      prompt += cost;
      pairs.add(pair);
    }
    final messages = [
      for (final p in pairs.reversed) ...[
        {'role': 'user', 'content': p.user},
        {'role': 'assistant', 'content': p.assistant},
      ],
      {'role': 'user', 'content': text},
    ];
    if (!model.free && budget == null) {
      throw const PlanRejected('service.error.limits');
    }
    if (!model.free && keyRemaining != null && model.rates.isNotEmpty) {
      if (model.quote(prompt, 16)!.compareTo(keyRemaining) > 0) {
        throw const PlanRejected('service.error.key_limit');
      }
      var low = 16, high = output;
      while (low < high) {
        final mid = (low + high + 1) ~/ 2;
        if (model.quote(prompt, mid)!.compareTo(keyRemaining) <= 0) {
          low = mid;
        } else {
          high = mid - 1;
        }
      }
      output = low;
    }
    final quote = model.quote(prompt, output);
    return RequestPlan(
      messages,
      prompt,
      output,
      quote,
      budgetWarning(
        limit: budget,
        used: spent,
        reserve: reserved,
        estimate: quote,
      ),
      budget == null || quote == null
          ? null
          : budget - spent - reserved - quote,
    );
  }
}
