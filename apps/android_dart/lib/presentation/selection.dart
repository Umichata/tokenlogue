import 'package:flutter/material.dart';
import '../domain/amount.dart';
import '../domain/catalogue.dart';
import '../domain/provider.dart';
import '../data/providers.dart';
import '../data/transport.dart';
import '../data/vault.dart';
import 'controls.dart';
import 'theme.dart';

typedef Selection = ({
  ModelChoice model,
  int tokens,
  int output,
  Amount? money,
  bool skip,
});

enum _Step { mode, model, limits }

Future<Service?> chooseChatProvider(
  BuildContext context,
  Translate t, {
  Service? current,
}) => showDialog<Service>(
  context: context,
  barrierDismissible: false,
  builder: (dialog) => AlertDialog(
    scrollable: true,
    constraints: const BoxConstraints(minWidth: 280, maxWidth: 420),
    title: Text(
      t(
        current == null
            ? 'creation.choose_provider'
            : 'connection.change_provider',
      ),
    ),
    content: Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      spacing: 12,
      children: [
        Text(
          t(
            current == null
                ? 'creation.choose_provider_help'
                : 'connection.choose_provider',
          ),
        ),
        for (final option in Service.values)
          OutlinedButton(
            style: OutlinedButton.styleFrom(
              minimumSize: const Size(0, 52),
              foregroundColor: ink,
              side: const BorderSide(color: border),
            ),
            onPressed: () => Navigator.pop(dialog, option),
            child: Row(
              children: [
                Icon(
                  current == option
                      ? Icons.check_circle_outline
                      : Icons.circle_outlined,
                ),
                const SizedBox(width: 10),
                Expanded(child: Text(option.label)),
                if (current == option) Text(t('connection.current')),
              ],
            ),
          ),
      ],
    ),
    actions: [
      TextButton(
        onPressed: () => Navigator.pop(dialog),
        child: Text(t('common.cancel')),
      ),
    ],
  ),
);

class SelectChat extends StatefulWidget {
  const SelectChat({
    super.key,
    required this.t,
    required this.api,
    required this.profile,
    required this.service,
    required this.onCancel,
    required this.onSelected,
    this.onChooseProvider,
    this.initialKeyStatus,
    this.existingTokens = 8192,
    this.existingOutput = 1024,
    this.moneyFor,
    this.changing = false,
  });
  final VoidCallback onCancel;
  final VoidCallback? onChooseProvider;
  final ValueChanged<Selection> onSelected;
  final KeyStatus? initialKeyStatus;
  final Translate t;
  final ProviderApi api;
  final UnlockedProfile profile;
  final Service service;
  final bool changing;
  final int existingTokens, existingOutput;
  final Future<Amount?> Function(Service)? moneyFor;
  @override
  State<SelectChat> createState() => _SelectChatState();
}

class _SelectChatState extends State<SelectChat> {
  late _Step step;
  Service get service => widget.service;
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
    paid = service == Service.vsegpt;
    step = paid ? _Step.model : _Step.mode;
    final status = widget.initialKeyStatus;
    keyStatus = status == KeyStatus.accepted
        ? 'selection.key.accepted'
        : status?.message ?? 'selection.key.not_checked';
    refresh();
  }

  Future<void> refresh() async {
    final s = service, key = widget.profile.keyFor(s), g = ++generation;
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
      final ordered =
          list
              .where(
                (m) => s != Service.openrouter || m.id != ModelChoice.router.id,
              )
              .toList()
            ..sort((a, b) {
              final order = a.name.toLowerCase().compareTo(
                b.name.toLowerCase(),
              );
              return order != 0 ? order : a.id.compareTo(b.id);
            });
      setState(
        () => choices = [
          if (s == Service.openrouter) ModelChoice.router,
          ...ordered,
        ],
      );
    } on ApiFailure catch (e) {
      if (mounted && generation == g) setState(() => error = e.label);
    } finally {
      if (mounted && generation == g) setState(() => loading = false);
    }
  }

  Future<void> check() async {
    final s = service, key = widget.profile.keyFor(s), g = generation;
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
    if (step == _Step.limits) {
      setState(() => step = _Step.model);
    } else if (step == _Step.model && service == Service.openrouter) {
      setState(() {
        step = _Step.mode;
        search = '';
      });
    } else if (service == Service.vsegpt && widget.onChooseProvider != null) {
      widget.onChooseProvider!();
    } else {
      widget.onCancel();
    }
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
          (m.name.toLowerCase().contains(search.toLowerCase().trim()) ||
              m.id.toLowerCase().contains(search.toLowerCase().trim())),
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
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) back();
      },
      child: ListView(
        key: ValueKey(step),
        padding: const EdgeInsets.all(20),
        children: [
          Row(
            children: [
              Image.asset(
                'assets/branding/tokenlogue-logo-transparent.png',
                width: 32,
                height: 32,
              ),
              const SizedBox(width: 8),
              Text('Tokenlogue', style: Theme.of(context).textTheme.titleLarge),
            ],
          ),
          const SizedBox(height: 12),
          if (step != _Step.limits) ...[
            Text(
              t(
                widget.changing
                    ? 'connection.change_provider'
                    : step == _Step.mode
                    ? 'mode.choose_first'
                    : service == Service.vsegpt
                    ? 'selection.models.vsegpt'
                    : paid
                    ? 'catalog.select_paid'
                    : 'catalog.select_free',
              ),
              style: Theme.of(context).textTheme.headlineSmall,
            ),
            if (step == _Step.model)
              TextFormField(
                initialValue: search,
                decoration: InputDecoration(
                  labelText: t('catalog.search'),
                  hintText: t('catalog.search_hint'),
                  prefixIcon: const Icon(Icons.search),
                ),
                onChanged: (v) => setState(() => search = v),
              ),
            Align(
              alignment: AlignmentDirectional.centerStart,
              child: TextButton(onPressed: back, child: Text(t('common.back'))),
            ),
            panelCard([
              Text(
                interpolate(t('selection.connection'), {
                  'provider': service.label,
                }),
              ),
              Text(interpolate(t(keyStatus), {'provider': service.label})),
              Align(
                alignment: AlignmentDirectional.centerStart,
                child: TextButton.icon(
                  onPressed:
                      checking ||
                          loading ||
                          widget.profile.keyFor(service) == null
                      ? null
                      : check,
                  icon: const Icon(Icons.key),
                  label: Text(t('selection.key.check')),
                ),
              ),
              if (checking || loading) const LinearProgressIndicator(),
              if (error.isNotEmpty)
                Text(interpolate(t(error), {'provider': service.label})),
            ]),
            TextButton.icon(
              onPressed: loading || checking ? null : refresh,
              icon: const Icon(Icons.refresh),
              label: Text(t('catalog.refresh')),
            ),
            if (step == _Step.model && service == Service.vsegpt)
              Text(
                t('selection.models.vsegpt_paid'),
                style: const TextStyle(color: muted),
              ),
            if (step == _Step.mode) ...[
              for (final p in [false, true])
                Padding(
                  padding: const EdgeInsets.only(top: 12),
                  child: panelCard([
                    Text(t(p ? 'mode.paid_title' : 'mode.free_title')),
                    Text(t(p ? 'workspace.mode_paid_help' : 'mode.free_help')),
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
              if (!loading && error.isEmpty && filtered.isEmpty)
                Text(t('catalog.none')),
              ...filtered.map(
                (m) => Padding(
                  padding: const EdgeInsets.only(top: 10),
                  child: panelCard([
                    Text(
                      m.id == ModelChoice.router.id
                          ? t('model.free_router')
                          : m.name,
                      style: const TextStyle(fontWeight: FontWeight.bold),
                    ),
                    Text(m.service.label),
                    Text(m.id),
                    if (m.rates.isEmpty)
                      Text(
                        t('workspace.pricing_unknown'),
                        style: const TextStyle(color: Colors.amber),
                      )
                    else ...[
                      Text(
                        "${t('price.prompt_million')} · ${m.maximum('prompt').times(1000000)} ${m.service.currency}",
                      ),
                      Text(
                        "${t('price.completion_million')} · ${m.maximum('completion').times(1000000)} ${m.service.currency}",
                      ),
                    ],
                    Align(
                      alignment: AlignmentDirectional.centerStart,
                      child: FilledButton(
                        onPressed: () => select(m),
                        child: Text(t('catalog.select')),
                      ),
                    ),
                  ], padding: const EdgeInsets.all(16)),
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
                decoration: InputDecoration(
                  labelText: t('limits.total'),
                  helperText: t('limits.total_help'),
                  helperMaxLines: 4,
                ),
                onChanged: (_) => setState(() {}),
              ),
              TextField(
                controller: output,
                keyboardType: TextInputType.number,
                decoration: InputDecoration(
                  labelText: t('limits.completion'),
                  helperText: t('limits.completion_help'),
                  helperMaxLines: 4,
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
                    helperText: interpolate(t('workspace.money_help'), {
                      'currency': service.currency,
                    }),
                    helperMaxLines: 4,
                    labelText: t(
                      'limits.money',
                    ).replaceAll('USD', service.currency),
                  ),
                  onChanged: (_) => setState(() {}),
                ),
              if (paid && !widget.changing)
                Material(
                  type: MaterialType.transparency,
                  child: CheckboxListTile(
                    value: skip,
                    onChanged: (v) => setState(() => skip = v ?? false),
                    title: Text(t('paid.no_confirmation')),
                  ),
                ),
              FilledButton(
                onPressed: valid
                    ? () => widget.onSelected((
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
          if (step == _Step.limits)
            TextButton(onPressed: back, child: Text(t('common.back'))),
        ],
      ),
    );
  }
}
