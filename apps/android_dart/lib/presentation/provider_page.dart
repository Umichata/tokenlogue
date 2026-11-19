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
  final values =
      <
        Service,
        ({
          String amount,
          String? limit,
          bool known,
          DateTime time,
          String status,
        })
      >{};
  final loading = <Service>{}, stale = <Service>{};
  final generation = <Service, int>{};
  final errors = <Service, String>{};
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
    try {
      final result = await api.account(service, key);
      if (!current()) return;
      values[service] = (
        amount: result.balance.toString(),
        limit: result.limit?.toString(),
        known: result.limitKnown,
        time: DateTime.now(),
        status: result.status,
      );
      stale.remove(service);
      errors.remove(service);
    } on ApiFailure catch (e) {
      if (current()) {
        stale.add(service);
        errors[service] = e.label;
      }
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
        Text(
          t('providers.title'),
          style: Theme.of(context).textTheme.headlineMedium,
        ),
        Text(t('providers.description')),
        const SizedBox(height: 16),
        panelCard([
          DropdownButtonFormField<String>(
            initialValue: widget.policy,
            decoration: InputDecoration(labelText: t('providers.default')),
            items: [
              DropdownMenuItem(
                value: 'manual',
                child: Text(t('creation.manual')),
              ),
              ...Service.values.map(
                (s) => DropdownMenuItem(value: s.name, child: Text(s.label)),
              ),
            ],
            onChanged: (v) {
              if (v != null) widget.setPolicy(v);
            },
          ),
          Text(
            widget.policy == 'manual'
                ? t('creation.manual_help')
                : interpolate(t('creation.provider_help'), {
                    'provider': Service.values.byName(widget.policy).label,
                  }),
          ),
        ]),
        const SizedBox(height: 16),
        DropdownButtonFormField<String>(
          initialValue: filter,
          decoration: InputDecoration(labelText: t('analytics.provider')),
          items: [
            DropdownMenuItem(
              value: 'all',
              child: Text(t('common.provider_all')),
            ),
            ...Service.values.map(
              (s) => DropdownMenuItem(value: s.name, child: Text(s.label)),
            ),
          ],
          onChanged: (v) {
            if (v != null) setState(() => filter = v);
          },
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
    if (validated != key || Service.detect(key) != s || busy) return;
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
    final canSave =
        validated == input.text.trim() &&
        status != null &&
        (status == KeyStatus.accepted ||
            s == Service.vsegpt &&
                {
                  KeyStatus.unverified,
                  KeyStatus.limited,
                  KeyStatus.unavailable,
                }.contains(status));
    return panelCard([
      Text(s.label, style: Theme.of(context).textTheme.titleLarge),
      Semantics(
        container: true,
        child: Text(
          t(
            !saved
                ? 'providers.status.not_configured'
                : page.profile.credentials[s.name]['verified'] == true
                ? 'providers.status.connected'
                : 'providers.status.unverified',
          ),
        ),
      ),
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
      if (status != null)
        Text(
          t(
            status == KeyStatus.accepted
                ? 'providers.checked'
                : canSave
                ? 'providers.unverified_help'
                : 'providers.check_failed',
          ),
        ),
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
                status == KeyStatus.accepted
                    ? 'providers.save'
                    : 'providers.save_unverified',
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
      if (account != null && account.status != 'ready')
        Text(t('providers.status.${account.status}')),
      if (stale && page.accounts.errors[s] != null)
        Text(t(page.accounts.errors[s]!)),
      if (stale)
        Text(
          t(
            account == null
                ? 'providers.balance_status.network_error'
                : 'providers.balance_status.stale',
          ),
        ),
      if (s == Service.openrouter)
        Text(
          account == null || !account.known
              ? t('providers.key_remaining_unknown')
              : account.limit == null
              ? t('providers.key_limit_not_set')
              : interpolate(t('providers.key_remaining'), {
                  'amount': account.limit,
                  'currency': 'USD',
                }),
        ),
      OutlinedButton.icon(
        onPressed: saved && !busy ? () => page.accounts.refresh(s) : null,
        icon: const Icon(Icons.refresh),
        label: Text(t('providers.refresh_balance')),
      ),
    ]);
  }
}
