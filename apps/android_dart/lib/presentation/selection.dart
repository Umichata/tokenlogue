import 'package:flutter/material.dart';
import '../domain/amount.dart';
import '../domain/catalogue.dart';
import '../domain/provider.dart';
import '../data/providers.dart';
import '../data/transport.dart';
import '../data/vault.dart';
import 'controls.dart';

typedef Selection = ({
  ModelChoice model,
  int tokens,
  int output,
  Amount? money,
  bool skip,
});

enum _Step { provider, mode, model, limits }

class SelectChat extends StatefulWidget {
  const SelectChat({
    super.key,
    required this.t,
    required this.api,
    required this.profile,
    required this.policy,
    this.existingTokens = 8192,
    this.existingOutput = 1024,
    this.moneyFor,
    this.changing = false,
    this.onConfigureKey,
  });
  final ValueChanged<Service>? onConfigureKey;
  final Translate t;
  final ProviderApi api;
  final UnlockedProfile profile;
  final String policy;
  final bool changing;
  final int existingTokens, existingOutput;
  final Future<Amount?> Function(Service)? moneyFor;
  @override
  State<SelectChat> createState() => _SelectChatState();
}

class _SelectChatState extends State<SelectChat> {
  _Step step = _Step.provider;
  Service? service;
  bool paid = false, skip = false, loading = false, checking = false;
  String error = '', keyStatus = '', search = '';
  int generation = 0;
  List<ModelChoice> choices = [];
  ModelChoice? chosen;
  late final tokens = TextEditingController(
        text: widget.existingTokens.toString(),
      ),
      output = TextEditingController(text: widget.existingOutput.toString());
  final money = TextEditingController();
  @override
  void initState() {
    super.initState();
    if (!widget.changing && widget.policy != 'manual') {
      openService(Service.values.byName(widget.policy));
    }
  }

  void openService(Service s) {
    service = s;
    keyStatus = '';
    paid = s == Service.vsegpt;
    step = paid ? _Step.model : _Step.mode;
    refresh();
  }

  Future<void> refresh() async {
    final s = service!, key = widget.profile.keyFor(s), g = ++generation;
    setState(() {
      loading = true;
      choices = [];
      error = '';
    });
    try {
      if (key == null) throw const ApiFailure('connection.no_key');
      final list = await widget.api.models(s, key);
      if (!mounted || generation != g || key != widget.profile.keyFor(s)) {
        return;
      }
      setState(
        () => choices = [
          if (s == Service.openrouter) ModelChoice.router,
          ...list,
        ],
      );
    } on ApiFailure catch (e) {
      if (mounted && generation == g) setState(() => error = e.label);
    } finally {
      if (mounted && generation == g) setState(() => loading = false);
    }
  }

  Future<void> check() async {
    final s = service!, key = widget.profile.keyFor(s), g = generation;
    if (key == null) return;
    setState(() => checking = true);
    final status = await widget.api.check(s, key);
    if (mounted && g == generation && key == widget.profile.keyFor(s)) {
      setState(() {
        checking = false;
        keyStatus = status == KeyStatus.accepted
            ? 'selection.key.accepted'
            : status.message;
      });
    }
  }

  void back() {
    setState(() {
      if (step == _Step.limits) {
        step = _Step.model;
        return;
      }
      if (step == _Step.model && service == Service.openrouter) {
        step = _Step.mode;
        return;
      }
      if (step != _Step.provider &&
          (widget.policy == 'manual' || widget.changing)) {
        step = _Step.provider;
        generation++;
        checking = false;
        return;
      }
      Navigator.of(context).pop();
    });
  }

  Future<void> select(ModelChoice m) async {
    final g = generation;
    final amount = await widget.moneyFor?.call(m.service);
    if (!mounted || generation != g) return;
    setState(() {
      chosen = m;
      step = _Step.limits;
      skip = false;
      money.text = amount?.toString() ?? '';
    });
  }

  @override
  void dispose() {
    generation++;
    tokens.dispose();
    output.dispose();
    money.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final t = widget.t;
    final filtered = choices.where(
      (m) =>
          m.free != paid &&
          (m.name.toLowerCase().contains(search.toLowerCase()) ||
              m.id.contains(search)),
    );
    final limit = Amount.parse(money.text.trim()),
        n = int.tryParse(tokens.text),
        cap = int.tryParse(output.text);
    final valid =
        n != null &&
        cap != null &&
        cap >= 16 &&
        n >= cap &&
        (!paid || limit != null && limit.coefficient.sign > 0);
    return PopScope(
      canPop:
          step == _Step.provider ||
          !widget.changing &&
              widget.policy != 'manual' &&
              (step == _Step.mode ||
                  service == Service.vsegpt && step == _Step.model),
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) back();
      },
      child: Scaffold(
        appBar: AppBar(
          leading: BackButton(onPressed: back),
          title: Text(
            t(widget.changing ? 'connection.change_provider' : 'chat.untitled'),
          ),
          actions: [
            IconButton(
              onPressed: () => Navigator.pop(context),
              tooltip: t('common.cancel'),
              icon: const Icon(Icons.close),
            ),
          ],
        ),
        body: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            if (step == _Step.provider)
              panelCard([
                Text(t('creation.choose_provider')),
                Text(t('creation.choose_provider_help')),
                for (final s in Service.values)
                  OutlinedButton(
                    onPressed: () => setState(() => openService(s)),
                    child: Text(s.label),
                  ),
              ]),
            if (step == _Step.mode || step == _Step.model) ...[
              panelCard([
                Text(service!.label),
                if (keyStatus.isNotEmpty)
                  Text(interpolate(t(keyStatus), {'provider': service!.label})),
                OutlinedButton.icon(
                  onPressed: checking || widget.profile.keyFor(service!) == null
                      ? null
                      : check,
                  icon: const Icon(Icons.verified_user),
                  label: Text(t('selection.key.check')),
                ),
                if (checking || loading) const LinearProgressIndicator(),
                if (error.isNotEmpty)
                  Text(interpolate(t(error), {'provider': service!.label})),
                if (widget.profile.keyFor(service!) == null &&
                    widget.onConfigureKey != null)
                  OutlinedButton(
                    onPressed: () {
                      Navigator.pop(context);
                      widget.onConfigureKey!(service!);
                    },
                    child: Text(
                      interpolate(t('connection.configure_key'), {
                        'provider': service!.label,
                      }),
                    ),
                  ),

                TextButton.icon(
                  onPressed: loading ? null : refresh,
                  icon: const Icon(Icons.refresh),
                  label: Text(t('catalog.refresh')),
                ),
              ]),
              if (step == _Step.mode) ...[
                Text(t('mode.choose_first')),
                for (final p in [false, true])
                  Padding(
                    padding: const EdgeInsets.only(top: 12),
                    child: panelCard([
                      Text(t(p ? 'mode.paid_title' : 'mode.free_title')),
                      Text(
                        t(p ? 'workspace.mode_paid_help' : 'mode.free_help'),
                      ),
                      FilledButton(
                        onPressed: choices.any((m) => m.free != p)
                            ? () => setState(() {
                                paid = p;
                                step = _Step.model;
                              })
                            : null,
                        child: Text(
                          t(p ? 'mode.choose_paid' : 'mode.choose_free'),
                        ),
                      ),
                    ]),
                  ),
              ],
              if (step == _Step.model) ...[
                Text(t(paid ? 'catalog.select_paid' : 'catalog.select_free')),
                TextField(
                  decoration: InputDecoration(labelText: t('catalog.search')),
                  onChanged: (v) => setState(() => search = v),
                ),
                if (!loading && error.isEmpty && filtered.isEmpty)
                  Text(t('catalog.none')),
                ...filtered.map(
                  (m) => Card(
                    child: ListTile(
                      title: Text(
                        m.id == ModelChoice.router.id
                            ? t('model.free_router')
                            : m.name,
                      ),
                      subtitle: Text(
                        [
                          m.id,
                          if (m.rates.isEmpty)
                            t('estimate.cost_unknown')
                          else ...[
                            "${t('price.prompt_million')} · ${m.maximum('prompt').times(1000000)} ${m.service.currency}",
                            "${t('price.completion_million')} · ${m.maximum('completion').times(1000000)} ${m.service.currency}",
                          ],
                        ].join('\n'),
                      ),
                      trailing: TextButton(
                        onPressed: () => select(m),
                        child: Text(t('catalog.select')),
                      ),
                    ),
                  ),
                ),
              ],
            ],
            if (step == _Step.limits)
              panelCard([
                Text(t('limits.configure')),
                Text(chosen!.name),
                TextField(
                  controller: tokens,
                  readOnly: widget.changing,
                  keyboardType: TextInputType.number,
                  decoration: InputDecoration(labelText: t('limits.total')),
                  onChanged: (_) => setState(() {}),
                ),
                TextField(
                  controller: output,
                  keyboardType: TextInputType.number,
                  decoration: InputDecoration(
                    labelText: t('limits.completion'),
                  ),
                  onChanged: (_) => setState(() {}),
                ),
                if (paid)
                  TextField(
                    controller: money,
                    keyboardType: const TextInputType.numberWithOptions(
                      decimal: true,
                    ),
                    decoration: InputDecoration(
                      labelText: t(
                        'limits.money',
                      ).replaceAll('USD', service!.currency),
                    ),
                    onChanged: (_) => setState(() {}),
                  ),
                if (paid && !widget.changing)
                  CheckboxListTile(
                    value: skip,
                    onChanged: (v) => setState(() => skip = v ?? false),
                    title: Text(t('paid.no_confirmation')),
                  ),
                FilledButton(
                  onPressed: valid
                      ? () => Navigator.pop<Selection>(context, (
                          model: chosen!,
                          tokens: n,
                          output: cap,
                          money: paid ? limit : null,
                          skip: skip,
                        ))
                      : null,
                  child: Text(
                    t(
                      widget.changing
                          ? 'connection.review'
                          : paid
                          ? 'limits.create_paid'
                          : 'limits.create_free',
                    ),
                  ),
                ),
              ]),
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: Text(t('common.cancel')),
            ),
          ],
        ),
      ),
    );
  }
}
