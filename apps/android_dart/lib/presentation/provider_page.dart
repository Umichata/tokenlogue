import 'package:flutter/material.dart';
import '../data/vault.dart';
import '../data/providers.dart';
import '../data/transport.dart';
import '../domain/provider.dart';
import 'controls.dart';

class AccountState extends ChangeNotifier {
  AccountState(this.profile, this.api);
  final UnlockedProfile profile;
  final ProviderApi api;
  final values = <Service, ({String amount, DateTime time, String status})>{};
  RouterKeyLimits? routerLimits;
  final loading = <Service>{}, stale = <Service>{};
  final generation = <Service, int>{};
  final errors = <Service, String>{};
  final keyChecks = <Service, KeyStatus>{};
  bool active = true;
  Future<void> refresh(Service service) async {
    final key = profile.keyFor(service);
    if (key == null || !active) return;
    final token = (generation[service] ?? 0) + 1;
    generation[service] = token;
    loading.add(service);
    notifyListeners();
    bool current() =>
        active &&
        !profile.disposed &&
        token == generation[service] &&
        key == profile.keyFor(service);
    Future<void> balance() async {
      try {
        final result = await api.account(service, key);
        if (!current()) return;
        if (service == Service.vsegpt) keyChecks[service] = KeyStatus.accepted;
        values[service] = (
          amount: result.balance.toString(),
          time: DateTime.now(),
          status: result.status,
        );
        stale.remove(service);
        errors.remove(service);
      } on ApiFailure catch (e) {
        if (!current()) return;
        if (service == Service.vsegpt) {
          keyChecks[service] = KeyStatus.fromFailure(service, e);
        }
        stale.add(service);
        errors[service] = switch (e.label) {
          'catalog.error.auth' => 'providers.balance_status.invalid',
          'catalog.error.policy' =>
            'providers.balance_status.restricted.${service.name}',
          'catalog.error.rate' => 'service.auth_rate',
          'catalog.error.schema' => 'service.response_format',
          'catalog.error.timeout' => 'service.auth_timeout',
          'catalog.error.tls' => 'service.auth_tls',
          _ => 'providers.balance_status.network_error',
        };
      }
    }

    Future<void> limits() async {
      try {
        final value = await api.routerKeyLimits(key);
        if (current()) {
          routerLimits = value;
          keyChecks[service] = KeyStatus.accepted;
        }
      } on ApiFailure catch (e) {
        if (current()) {
          routerLimits = null;
          keyChecks[service] = KeyStatus.fromFailure(service, e);
        }
      }
    }

    try {
      await Future.wait([
        balance(),
        if (service == Service.openrouter) limits(),
      ]);
    } finally {
      if (current()) {
        loading.remove(service);
        notifyListeners();
      }
    }
  }

  void changed(Service service) {
    generation[service] = (generation[service] ?? 0) + 1;
    values.remove(service);
    errors.remove(service);
    keyChecks.remove(service);
    if (service == Service.openrouter) routerLimits = null;
    stale.remove(service);
    loading.remove(service);
    if (active) notifyListeners();
  }

  @override
  void dispose() {
    active = false;
    super.dispose();
  }
}

class ProviderPage extends StatefulWidget {
  const ProviderPage({
    super.key,
    required this.t,
    required this.vault,
    required this.profile,
    required this.api,
    required this.accounts,
    required this.policy,
    required this.setPolicy,
    required this.onKeyChanged,
    this.initial,
    this.languagePicker,
  });
  final Translate t;
  final ProfileVault vault;
  final UnlockedProfile profile;
  final ProviderApi api;
  final AccountState accounts;
  final String policy;
  final ValueChanged<String> setPolicy;
  final ValueChanged<Service> onKeyChanged;
  final Service? initial;
  final Widget? languagePicker;
  @override
  State<ProviderPage> createState() => _ProviderPageState();
}

class _ProviderPageState extends State<ProviderPage> {
  late String filter = widget.initial?.name ?? 'all';
  @override
  Widget build(BuildContext context) {
    final t = widget.t;
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        pageHeading(t('providers.title'), widget.languagePicker),
        const SizedBox(height: 12),
        Text(t('providers.description')),
        const SizedBox(height: 12),
        PageFilter<String>(
          label: t('analytics.provider'),
          value: filter,
          options: {
            'all': t('common.provider_all'),
            for (final s in Service.values) s.name: s.label,
          },
          onSelected: (v) => setState(() => filter = v),
        ),
        const SizedBox(height: 16),
        PageFilter<String>(
          label: t('providers.default'),
          value: widget.policy,
          options: {
            'manual': t('creation.manual'),
            for (final s in Service.values) s.name: s.label,
          },
          onSelected: widget.setPolicy,
        ),
        const SizedBox(height: 8),
        Text(
          widget.policy == 'manual'
              ? t('creation.manual_help')
              : interpolate(t('creation.provider_help'), {
                  'provider': Service.values.byName(widget.policy).label,
                }),
          style: const TextStyle(fontSize: 12),
        ),
        for (final s in Service.values.where(
          (s) => filter == 'all' || s.name == filter,
        ))
          Padding(
            padding: const EdgeInsets.only(top: 16),
            child: _ServiceCard(key: ValueKey(s), page: widget, service: s),
          ),
      ],
    );
  }
}

class _ServiceCard extends StatefulWidget {
  const _ServiceCard({super.key, required this.page, required this.service});
  final ProviderPage page;
  final Service service;
  @override
  State<_ServiceCard> createState() => _ServiceCardState();
}

class _ServiceCardState extends State<_ServiceCard> {
  final input = TextEditingController();
  String? validated;
  KeyStatus? status;
  int revision = 0;
  bool busy = false;
  ProviderPage get page => widget.page;
  Service get s => widget.service;
  Future<void> check() async {
    final value = input.text.trim(), request = ++revision;
    if (Service.detect(value) != s) return;
    setState(() {
      busy = true;
      validated = null;
    });
    final outcome = await page.api.check(s, value);
    if (mounted &&
        !page.profile.disposed &&
        request == revision &&
        value == input.text.trim()) {
      setState(() {
        status = outcome;
        validated = value;
        busy = false;
      });
    }
  }

  Future<void> save() async {
    final key = input.text.trim();
    if (validated != key ||
        Service.detect(key) != s ||
        busy ||
        !(status == KeyStatus.accepted ||
            status?.maySaveUnverified(s) == true)) {
      return;
    }
    setState(() => busy = true);
    try {
      await page.vault.saveKey(
        page.profile,
        s,
        key,
        status == KeyStatus.accepted,
      );
      if (!mounted || page.profile.disposed) return;
      input.clear();
      validated = null;
      status = null;
      page.accounts.changed(s);
      page.onKeyChanged(s);
      await page.accounts.refresh(s);
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  void dispose() {
    revision++;
    input.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final t = page.t;
    final detected = Service.detect(input.text),
        saved = page.profile.keyFor(s) != null;
    final account = page.accounts.values[s],
        stale = page.accounts.stale.contains(s);
    final savedStatus = !saved
        ? 'providers.status.not_configured'
        : switch (page.accounts.keyChecks[s]) {
            KeyStatus.accepted
                when !stale && account?.status == 'subscription_required' =>
              'providers.status.subscription_required',
            KeyStatus.accepted when !stale && account?.status == 'warning' =>
              'providers.status.warning',
            KeyStatus.accepted => 'providers.status.connected',
            KeyStatus.invalid => 'providers.status.invalid',
            KeyStatus.restricted => 'providers.status.restricted',
            null when page.profile.credentials[s.name]['verified'] == true =>
              'providers.status.connected',
            _ => 'providers.status.unverified',
          };
    final limits = page.accounts.routerLimits;
    final canSave =
        validated == input.text.trim() &&
        (status == KeyStatus.accepted || status?.maySaveUnverified(s) == true);
    return panelCard([
      Text(s.label, style: Theme.of(context).textTheme.titleLarge),
      Text(t(saved ? 'providers.saved_key' : 'providers.no_saved_key')),
      Text(
        interpolate(t('connection.shared_key'), {'provider': s.label}),
        style: const TextStyle(fontSize: 12),
      ),
      Semantics(container: true, child: Text(t(savedStatus))),
      SecretField(
        controller: input,
        label: interpolate(t('providers.form_key'), {'provider': s.label}),
        t: t,
        hint: interpolate(t('providers.form_key_hint'), {'provider': s.label}),
        changed: (_) => setState(() {
          revision++;
          validated = null;
          status = null;
          busy = false;
        }),
      ),
      if (input.text.isNotEmpty)
        Text(
          detected == null
              ? t('providers.unknown_prefix')
              : detected != s
              ? t('catalog.error.key_mismatch')
              : interpolate(t('providers.detected'), {'provider': s.label}),
        ),
      if (status case final outcome?) Text(t(outcome.message)),
      if (canSave && status != KeyStatus.accepted)
        Text(t('providers.unverified_help')),
      Wrap(
        spacing: 8,
        children: [
          FilledButton(
            onPressed: detected == s && !busy ? check : null,
            child: Text(t('providers.check')),
          ),
          OutlinedButton(
            onPressed: canSave && !busy ? save : null,
            child: Text(
              t(
                status?.maySaveUnverified(s) == true
                    ? 'providers.save_unverified'
                    : 'providers.save',
              ),
            ),
          ),
        ],
      ),
      if (page.accounts.loading.contains(s)) const LinearProgressIndicator(),
      Semantics(
        container: true,
        liveRegion: true,
        child: Text(
          account == null
              ? interpolate(t('providers.balance_unavailable'), {
                  'provider': s.label,
                })
              : interpolate(t('providers.balance'), {
                  'provider': s.label,
                  'currency': s.currency,
                  'amount': account.amount,
                }),
        ),
      ),
      if (account != null &&
          account.status != 'ready' &&
          t(savedStatus) != t('providers.balance_status.${account.status}'))
        Text(t('providers.balance_status.${account.status}')),
      if (stale && page.accounts.errors[s] != null)
        Text(t(page.accounts.errors[s]!)),
      if (stale && account != null) Text(t('providers.balance_status.stale')),
      if (s == Service.openrouter) ...[
        Text(
          limits == null
              ? t('providers.key_remaining_unknown')
              : limits.amount == null
              ? t('providers.key_limit_not_set')
              : interpolate(t('providers.key_remaining'), {
                  'amount': limits.amount.toString(),
                  'currency': 'USD',
                }),
        ),
        if (limits?.daily case final daily?)
          Text(
            interpolate(t('providers.daily_free_quota'), {
              'remaining': daily.remaining,
              'limit': daily.limit,
            }),
          ),
      ],
      OutlinedButton.icon(
        onPressed: saved && !busy ? () => page.accounts.refresh(s) : null,
        icon: const Icon(Icons.refresh),
        label: Text(t('providers.refresh_balance')),
      ),
    ]);
  }
}
