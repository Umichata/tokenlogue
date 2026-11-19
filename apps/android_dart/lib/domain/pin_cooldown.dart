/// Use elapsed device time for the lock. A reboot creates a new monotonic epoch.
class PinCooldown {
  static const maximum = 300000;
  static int normalize(Map<String, dynamic> record, int elapsed, int boot) {
    final attempts = record['attempts'];
    if (attempts is! int || attempts < 0 || attempts > 3 || elapsed < 0) {
      throw const FormatException('pin_state');
    }
    if (attempts < 3) return 0;
    final deadline = record['deadline'],
        oldBoot = record['boot'],
        prior = record['lock_remaining'] ?? maximum;
    if (deadline is! int ||
        oldBoot is! int ||
        prior is! int ||
        prior < 1 ||
        prior > maximum) {
      throw const FormatException('pin_lock');
    }
    final last =
        record['last_elapsed'] as int? ??
        (deadline - maximum).clamp(0, deadline);
    final reset = oldBoot != boot || boot < 0 && elapsed < last;
    final remaining =
        (reset
                ? prior - elapsed
                : elapsed < last
                ? prior
                : deadline - elapsed)
            .clamp(0, prior);
    if (remaining == 0) {
      clear(record);
      return 0;
    }
    record.addAll({
      'boot': boot,
      'deadline': elapsed + remaining,
      'last_elapsed': elapsed,
      'lock_remaining': remaining,
    });
    return remaining;
  }

  static void arm(Map<String, dynamic> record, int elapsed, int boot) {
    record.addAll({
      'attempts': 3,
      'boot': boot,
      'deadline': elapsed + maximum,
      'last_elapsed': elapsed,
      'lock_remaining': maximum,
    });
  }

  static void clear(Map<String, dynamic> record) {
    record['attempts'] = 0;
    for (final key in ['boot', 'deadline', 'last_elapsed', 'lock_remaining']) {
      record.remove(key);
    }
  }
}
