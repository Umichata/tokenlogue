enum Service {
  openrouter('OpenRouter', 'USD', ['sk-or-v1-']),
  vsegpt('VSEGPT', 'RUB', ['sk-or-vv-', 'sk-or-vis']);

  const Service(this.label, this.currency, this.prefixes);
  final String label;
  final String currency;
  final List<String> prefixes;

  static Service? detect(String value) {
    final key = value.trim();
    if (key.codeUnits.any((c) => c < 33 || c > 126)) return null;
    for (final service in values) {
      for (final prefix in service.prefixes) {
        if (key.startsWith(prefix) &&
            key.substring(prefix.length).replaceAll('-', '').isNotEmpty) {
          return service;
        }
      }
    }
    return null;
  }
}
