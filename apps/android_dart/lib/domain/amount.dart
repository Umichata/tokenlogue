/// An exact base-ten amount. Keep the original provider currency alongside it.
final class Amount implements Comparable<Amount> {
  Amount._(this.coefficient, this.scale);
  final BigInt coefficient;
  final int scale;
  static final zero = Amount._(BigInt.zero, 0);
  static final _grammar = RegExp(
    r'^(-?)([0-9]+)(?:\.([0-9]+))?(?:[eE]([+-]?[0-9]+))?$',
  );
  static Amount? parse(Object? input) {
    if (input is! int && input is! String) return null;
    final s = input.toString();
    if (s.length > 180) return null;
    final m = _grammar.firstMatch(s);
    if (m == null) return null;
    final exp = int.tryParse(m[4] ?? '0');
    if (exp == null || exp.abs() > 100) return null;
    final fraction = m[3] ?? '';
    return _normalize(
      BigInt.parse('${m[1]}${m[2]}$fraction'),
      fraction.length - exp,
    );
  }

  static Amount _normalize(BigInt coefficient, int scale) {
    if (coefficient == BigInt.zero) return zero;
    if (scale < 0) {
      return Amount._(coefficient * BigInt.from(10).pow(-scale), 0);
    }
    while (scale > 0 && coefficient.remainder(BigInt.from(10)) == BigInt.zero) {
      coefficient = coefficient ~/ BigInt.from(10);
      scale--;
    }
    return Amount._(coefficient, scale);
  }

  BigInt _at(int digits) => coefficient * BigInt.from(10).pow(digits - scale);
  Amount operator +(Amount other) {
    final digits = scale > other.scale ? scale : other.scale;
    return _normalize(_at(digits) + other._at(digits), digits);
  }

  Amount operator -(Amount other) =>
      this + Amount._(-other.coefficient, other.scale);
  Amount times(int n) => _normalize(coefficient * BigInt.from(n), scale);

  /// Display precision only. Never feed rounded values back into accounting.
  Amount forDisplay({bool upperBound = false}) {
    if (scale <= 4) return this;
    final divisor = BigInt.from(10).pow(scale - 4);
    final difference = coefficient.remainder(divisor);
    var rounded = coefficient ~/ divisor;
    if (upperBound
        ? difference > BigInt.zero
        : difference.abs() * BigInt.two >= divisor) {
      rounded += BigInt.from(coefficient.sign);
    }
    return _normalize(rounded, 4);
  }

  @override
  int compareTo(Amount other) => (this - other).coefficient.sign;
  @override
  bool operator ==(Object other) =>
      other is Amount &&
      coefficient == other.coefficient &&
      scale == other.scale;
  @override
  int get hashCode => Object.hash(coefficient, scale);
  @override
  String toString() {
    final digits = coefficient.abs().toString().padLeft(scale + 1, '0');
    final sign = coefficient.isNegative ? '-' : '';
    if (scale == 0) return '$sign$digits';
    return '$sign${digits.substring(0, digits.length - scale)}.${digits.substring(digits.length - scale)}';
  }
}

bool budgetWarning({
  required Amount? limit,
  required Amount used,
  required Amount reserve,
  required Amount? estimate,
}) {
  if (limit == null ||
      estimate != null && estimate.compareTo(Amount.zero) <= 0) {
    return false;
  }
  return estimate == null ||
      (limit - used - reserve - estimate).times(10).compareTo(limit) <= 0;
}
