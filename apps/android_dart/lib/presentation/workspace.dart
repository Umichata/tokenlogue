import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../domain/amount.dart';
import '../domain/catalogue.dart';
import '../domain/provider.dart';
import '../domain/request_plan.dart';
import '../data/chat_service.dart';
import '../data/chat_store.dart';
import '../data/journal.dart';
import '../data/providers.dart';
import '../data/session.dart';
import '../data/transport.dart';
import '../data/vault.dart';
import 'analytics_page.dart';
import 'controls.dart';
import 'message_body.dart';
import 'provider_page.dart';
import 'selection.dart';
import 'theme.dart';

class Workspace extends StatefulWidget {
  const Workspace({
    super.key,
    required this.session,
    required this.api,
    required this.vault,
    required this.t,
    required this.onLock,
    required this.onDelete,
    required this.language,
    required this.setLanguage,
  });
  final Session session;
  final ProviderApi api;
  final ProfileVault vault;
  final Translate t;
  final VoidCallback onLock, onDelete;
  final String language;
  final ValueChanged<String> setLanguage;
  @override
  State<Workspace> createState() => _WorkspaceState();
}

class _WorkspaceState extends State<Workspace> {
  final composer = TextEditingController();
  late final accounts = AccountState(widget.session.profile, widget.api);
  int page = 0, sequence = 0;
  int _editVersion = 0, _viewVersion = 0;
  String? selected;
  String policy = 'manual', error = '';
  bool showChats = false, sending = false, loading = true;
  List<ChatRecord> chats = [];
  List<JournalRow> rows = [];
  List<({String turn, String role, String body})> messages = [];
  JournalRow settings = {};
  Amount? budget;
  Service? providerFilter;
  ChatStore get store => widget.session.store;
  ChatRecord? get chat => chats.where((c) => c.id == selected).firstOrNull;
  bool get alive => mounted && !widget.session.closing;
  Translate get t => widget.t;
  @override
  void initState() {
    super.initState();
    accounts.addListener(update);
    unawaited(
      load(first: true).catchError((Object e) {
        if (alive) {
          widget.onLock();
        }
      }),
    );
  }

  void update() {
    if (alive) setState(() {});
  }

  String label(Object e) => switch (e) {
    ApiFailure(:final label) => t(label),
    PlanRejected(:final message) => t(message),
    _ => t('providers.operation_failed'),
  };
  Future<void> run(Future<void> Function() action) async {
    final version = _viewVersion;
    try {
      await action();
    } catch (e) {
      if (alive && version == _viewVersion) setState(() => error = label(e));
    }
  }

  Future<void> load({String? target, bool first = false}) async {
    final g = ++sequence, editVersion = _editVersion, oldChat = selected;
    await widget.session.flush();
    final list = await store.chats();
    final saved = target ?? selected ?? await store.preference('selected');
    final c = list.where((c) => c.id == saved).firstOrNull ?? list.firstOrNull;
    final all = await store.journal(),
        history = c == null
            ? <({String turn, String role, String body})>[]
            : await store.history(c.id);
    final cfg = c == null ? <String, Object?>{} : await store.settings(c.id);
    final limit = c == null ? null : await store.limitFor(c.id, c.service);
    final p = await store.preference('new_provider');
    if (!alive || g != sequence) return;
    setState(() {
      chats = list;
      rows = all;
      messages = history;
      settings = cfg;
      budget = limit;
      policy = p ?? 'manual';
      selected = c?.id;
      loading = false;
      final draft = c?.draft ?? '';
      if ((oldChat != c?.id || _editVersion == editVersion) &&
          composer.text != draft) {
        composer.value = TextEditingValue(
          text: draft,
          selection: TextSelection.collapsed(offset: draft.length),
        );
      }
    });
    if (c != null) await store.setPreference('selected', c.id);
    if (first) {
      for (final service in Service.values) {
        if (alive && widget.session.profile.keyFor(service) != null) {
          unawaited(accounts.refresh(service));
        }
      }
    }
  }

  Future<void> selectChat(String id) async {
    _viewVersion++;
    if (mounted) setState(() => error = '');
    widget.session.sending.invalidate();
    await load(target: id);
    if (alive) setState(() => showChats = false);
  }

  Future<void> selectPage(int i) async {
    _viewVersion++;
    widget.session.sending.invalidate();
    await widget.session.flush();
    if (alive) {
      setState(() {
        page = i;
        error = '';
        showChats = false;
      });
    }
  }

  Future<void> editText() async {
    _editVersion++;
    final c = chat;
    if (c == null) return;
    await widget.session.writeDraft(c.id, composer.text);
  }

  Future<void> newChat({bool change = false}) async {
    final c = chat;
    if (change &&
        (c == null ||
            sending ||
            totals(
              rows.where((r) => r['chat'] == c.id).toList(),
              c.service,
            ).blocked)) {
      throw const PlanRejected('service.previous_unknown');
    }
    final originalProfile = widget.session.profile;
    final identities = {
      for (final s in Service.values) s: originalProfile.keyFor(s),
    };
    final choice = await Navigator.push<Selection>(
      context,
      MaterialPageRoute(
        builder: (_) => SelectChat(
          t: t,
          api: widget.api,
          profile: originalProfile,
          policy: policy,
          changing: change,
          onConfigureKey: (s) {
            if (alive) {
              providerFilter = s;
              unawaited(selectPage(1));
            }
          },
          existingTokens: change
              ? settings['token_limit'] as int? ?? 8192
              : 8192,
          existingOutput: change
              ? settings['response_limit'] as int? ?? 1024
              : 1024,
          moneyFor: change ? (s) => store.limitFor(c!.id, s) : null,
        ),
      ),
    );
    if (!mounted || choice == null || !alive) return;
    if (identities[choice.model.service] !=
        originalProfile.keyFor(choice.model.service)) {
      throw const PlanRejected('connection.stale');
    }
    if (change &&
        !await confirm(
          context,
          t('connection.confirm_title'),
          interpolate(t('connection.context_warning'), {
            'provider': choice.model.service.label,
          }),
          t('common.cancel'),
          t('connection.change_provider'),
        )) {
      return;
    }
    if (!alive) return;
    await widget.session.flush();
    final id = change ? c!.id : newId();
    await store.configure(
      existing: change ? id : null,
      id: id,
      title: t('chat.untitled'),
      model: choice.model,
      tokens: choice.tokens,
      output: choice.output,
      budget: choice.money,
      skip: choice.skip,
      reconnect: change,
    );
    await selectChat(id);
  }

  Future<void> rename() async {
    final c = chat;
    if (c == null) return;
    var value = c.title;
    final accepted = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(t('chat.rename_title')),
        content: TextFormField(
          initialValue: c.title,
          autofocus: true,
          onChanged: (v) => value = v,
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: Text(t('common.cancel')),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: Text(t('chat.save')),
          ),
        ],
      ),
    );
    if (accepted != true || !alive || value.trim().isEmpty) return;
    await store.rename(c.id, value);
    await load();
  }

  Future<void> remove() async {
    final c = chat;
    if (c == null) return;
    if (!await confirm(
      context,
      t('chat.delete_title'),
      interpolate(t('chat.delete_body'), {'title': c.title}),
      t('common.cancel'),
      t('chat.delete'),
    )) {
      return;
    }
    if (!alive) return;
    widget.session.sending.invalidate();
    await widget.session.flush();
    await store.deleteChat(c.id);
    await load();
  }

  Future<void> editLimits() async {
    final c = chat;
    if (c == null) return;
    var token = '${settings['token_limit'] ?? 8192}',
        cap = '${settings['response_limit'] ?? 1024}',
        amount = budget?.toString() ?? '';
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        scrollable: true,
        title: Text(t('limits.dialog')),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextFormField(
              initialValue: token,
              decoration: InputDecoration(labelText: t('limits.total')),
              keyboardType: TextInputType.number,
              onChanged: (v) => token = v,
            ),
            TextFormField(
              initialValue: cap,
              decoration: InputDecoration(labelText: t('limits.completion')),
              keyboardType: TextInputType.number,
              onChanged: (v) => cap = v,
            ),
            if (!c.free)
              TextFormField(
                initialValue: amount,
                decoration: InputDecoration(
                  labelText: t(
                    'limits.money',
                  ).replaceAll('USD', c.service.currency),
                ),
                keyboardType: const TextInputType.numberWithOptions(
                  decimal: true,
                ),
                onChanged: (v) => amount = v,
              ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: Text(t('common.cancel')),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: Text(t('limits.save')),
          ),
        ],
      ),
    );
    if (!mounted || ok != true || !alive) return;
    final next = Amount.parse(amount),
        n = int.tryParse(token),
        output = int.tryParse(cap);
    if (n == null ||
        output == null ||
        output < 16 ||
        n < output ||
        !c.free && (next == null || next.coefficient.sign <= 0)) {
      throw const PlanRejected('service.error.limits');
    }
    if (!c.free &&
        budget != null &&
        next!.compareTo(budget!) > 0 &&
        !await confirm(
          context,
          t('paid.increase_title'),
          '${budget!} → $next ${c.service.currency}',
          t('common.cancel'),
          t('paid.confirm_increase'),
        )) {
      return;
    }
    if (!alive) return;
    final price = ModelChoice.fromJson(
      jsonDecode(settings['price'] as String) as Payload,
    );
    await store.configure(
      existing: c.id,
      id: c.id,
      title: c.title,
      model: price,
      tokens: n,
      output: output,
      budget: next,
      skip: settings['skip_paid'] == 1,
      reconnect: false,
    );
    widget.session.sending.invalidate();
    await load();
  }

  Future<void> send({String? retry}) async {
    if (sending || chat == null) return;
    setState(() {
      sending = true;
      error = '';
    });
    try {
      await widget.session.flush();
      if (!alive) return;
      final c = (await store.chats()).firstWhere((c) => c.id == selected);
      final q = await widget.session.sending.preview(c, retry: retry);
      if (!mounted || !alive || selected != c.id || page != 0) {
        widget.session.sending.invalidate();
        return;
      }
      var confirmed = false;
      if (!q.model.free &&
          (!q.skip || q.plan.warning || q.plan.reserve == null)) {
        final choice = await showDialog<String>(
          context: context,
          builder: (ctx) => AlertDialog(
            scrollable: true,
            title: Text(
              t(q.plan.warning ? 'budget_warning.title' : 'paid.confirm_title'),
            ),
            content: Text(
              '${q.model.name}\n${t('paid.prompt_estimate')}: ${q.plan.prompt}\n${t('paid.completion_maximum')}: ${q.plan.completion}\n${t('budget_warning.estimate')}: ${q.plan.reserve ?? '—'} ${q.model.service.currency}\n${t('paid.remaining')}: ${q.plan.projected ?? '—'} ${q.model.service.currency}',
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(ctx),
                child: Text(t('common.cancel')),
              ),
              if (q.plan.warning)
                TextButton(
                  onPressed: () => Navigator.pop(ctx, 'edit'),
                  child: Text(t('budget_warning.edit')),
                ),
              FilledButton(
                onPressed: () => Navigator.pop(ctx, 'send'),
                child: Text(
                  t(q.plan.warning ? 'budget_warning.send' : 'paid.send'),
                ),
              ),
            ],
          ),
        );
        if (!alive || choice != 'send') {
          widget.session.sending.invalidate();
          if (alive && choice == 'edit') await editLimits();
          return;
        }
        confirmed = true;
      }
      await widget.session.dispatch(q, confirmed);
      if (alive) unawaited(accounts.refresh(c.service));
    } on ChangedPrice catch (change) {
      if (mounted &&
          alive &&
          await confirm(
            context,
            t('paid.price_changed'),
            t('paid.confirm_required'),
            t('common.cancel'),
            t('paid.confirm_prices'),
          ) &&
          alive) {
        await store.confirmPrice(change.chat, change.version, change.current);
        // Fresh preview only. A price confirmation is never consent to dispatch.
        await widget.session.sending.preview(
          (await store.chats()).firstWhere((c) => c.id == change.chat),
        );
        widget.session.sending.invalidate();
      }
    } finally {
      if (alive) {
        await load();
        if (alive) setState(() => sending = false);
      }
    }
  }

  Future<void> release(String id) async {
    final c = chat;
    if (c == null) return;
    final a = rows.firstWhere((a) => a['id'] == id);
    if (await confirm(
          context,
          t('reserve.release_title'),
          interpolate(t('reserve.release_body'), {
            'tokens': a['reserved_tokens'],
            'amount': '${a['reserved_cost'] ?? '—'} ${a['currency']}',
          }),
          t('common.cancel'),
          t('reserve.release'),
        ) &&
        alive) {
      await store.releaseUnknown(c.id, id);
      await load();
    }
  }

  String mask(Service s) {
    final key = widget.session.profile.keyFor(s);
    if (key == null) {
      return interpolate(t('connection.missing_key'), {'provider': s.label});
    }
    final prefix = s.prefixes.where(key.startsWith).firstOrNull;
    return prefix != null &&
            key
                    .substring(prefix.length)
                    .replaceFirst(RegExp('^-+'), '')
                    .length >=
                12
        ? '•••• ${key.substring(key.length - 4)}'
        : '••••';
  }

  Future<void> menu() async {
    final c = chat;
    final value = await showDialog<String>(
      context: context,
      builder: (ctx) => SimpleDialog(
        title: Text(t('chat.options')),
        children: [
          if (c != null) ...[
            ListTile(
              title: Text(t('connection.title')),
              subtitle: Text(
                '${c.service.label} · ${mask(c.service)}\n${c.model} · ${c.service.currency}',
              ),
            ),
            for (final action in [
              if (MediaQuery.sizeOf(context).height -
                      MediaQuery.viewInsetsOf(context).bottom <
                  560) ...[
                'chat.rename',
                'chat.delete_chat',
              ],
              'connection.configure_key',
              'connection.change_provider',
              'limits.dialog',
            ])
              SimpleDialogOption(
                onPressed: () => Navigator.pop(ctx, action),
                child: Text(
                  interpolate(t(action), {'provider': c.service.label}),
                ),
              ),
          ],
          if (c != null && !c.free)
            SwitchListTile(
              value: settings['skip_paid'] == 1,
              title: Text(t('metrics.without_confirmation')),
              onChanged: (_) => Navigator.pop(ctx, 'toggle_confirm'),
            ),
          for (final action in [
            'language.label',
            'protection_panel.open',
            'profile_deletion.entry',
          ])
            SimpleDialogOption(
              onPressed: () => Navigator.pop(ctx, action),
              child: Text(
                interpolate(t(action), {'provider': c?.service.label ?? ''}),
              ),
            ),
          SimpleDialogOption(
            onPressed: () => Navigator.pop(ctx),
            child: Text(t('common.cancel')),
          ),
        ],
      ),
    );
    if (!alive) return;
    switch (value) {
      case 'chat.rename':
        await rename();
      case 'chat.delete_chat':
        await remove();
      case 'toggle_confirm':
        if (c != null) await toggleConfirmations(c, settings['skip_paid'] != 1);
      case 'connection.configure_key':
        providerFilter = c?.service;
        await selectPage(1);
      case 'connection.change_provider':
        await newChat(change: true);
      case 'limits.dialog':
        await editLimits();
      case 'language.label':
        widget.setLanguage(widget.language == 'ru' ? 'en' : 'ru');
      case 'profile_deletion.entry':
        widget.onDelete();
      case 'protection_panel.open':
        await protection();
    }
  }

  Future<void> protection() async {
    final available = await widget.vault.canRecover();
    if (!mounted || !alive) return;
    await showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        alignment: Alignment.topRight,
        backgroundColor: panel,
        insetPadding: const EdgeInsets.fromLTRB(12, 64, 12, 12),
        title: Row(
          children: [
            Expanded(
              child: Text(
                t('session_watch.menu_title'),
                style: Theme.of(ctx).textTheme.titleMedium,
              ),
            ),
            IconButton(
              tooltip: t('protection_panel.close'),
              onPressed: () => Navigator.pop(ctx),
              icon: const Icon(Icons.close),
            ),
          ],
        ),
        scrollable: true,
        content: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 340),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            spacing: 12,
            children: [
              Text(t('protection_panel.android_policy')),
              Text(
                t(
                  available
                      ? 'recovery.protection_notice_android'
                      : 'recovery.protection_notice_android_unavailable',
                ),
                style: const TextStyle(color: muted),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget list() => Material(
    color: panel,
    child: Column(
      children: [
        Padding(
          padding: const EdgeInsets.all(16),
          child: Row(
            children: [
              Image.asset(
                'assets/branding/tokenlogue-logo-transparent.png',
                width: 32,
              ),
              const SizedBox(width: 10),
              const Expanded(
                child: Text('Tokenlogue', style: TextStyle(fontSize: 22)),
              ),
            ],
          ),
        ),
        FilledButton.icon(
          onPressed: () => run(() => newChat()),
          icon: const Icon(Icons.add),
          label: Text(t('chat.untitled')),
        ),
        const Divider(),
        Expanded(
          child: ListView(
            children: [
              for (final c in chats)
                ListTile(
                  selected: c.id == selected,
                  leading: const Icon(Icons.chat_bubble_outline),
                  title: Text(
                    c.title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  subtitle: Text(
                    '${t(c.free ? 'mode.free_title' : 'mode.paid_title')} · ${c.model}',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  onTap: () => run(() => selectChat(c.id)),
                ),
            ],
          ),
        ),
        TextButton.icon(
          onPressed: widget.onLock,
          icon: const Icon(Icons.lock),
          label: Text(t('chat.lock')),
        ),
      ],
    ),
  );
  String accountText(Service s) {
    final a = accounts.values[s];
    if (a == null) {
      return interpolate(t('providers.balance_unavailable'), {
        'provider': s.label,
      });
    }
    final label = accounts.stale.contains(s)
        ? 'metrics.account_stale'
        : accounts.loading.contains(s)
        ? 'metrics.account_updating'
        : 'metrics.account_current';
    return interpolate(t(label), {
      'provider': s.label,
      'amount': '${a.amount} ${s.currency}',
    });
  }

  String keyLimitText(Service s) {
    final a = accounts.values[s];
    if (a == null || !a.known) return t('providers.key_remaining_unknown');
    return a.limit == null
        ? t('providers.key_limit_not_set')
        : interpolate(t('providers.key_remaining'), {
            'amount': a.limit,
            'currency': s.currency,
          });
  }

  String estimate(ChatRecord c, List<JournalRow> rows) {
    final text = composer.text.trim();
    if (text.isEmpty) return t('estimate.empty');
    final config = settings['price'];
    if (config is! String) return t('estimate.unavailable');
    final model = ModelChoice.fromJson(jsonDecode(config) as Payload),
        total = totals(rows, c.service);
    try {
      final pairs = <ChatPair>[];
      for (final m in messages.where((m) => m.role == 'user')) {
        final a = messages
            .where((a) => a.turn == m.turn && a.role == 'assistant')
            .firstOrNull;
        if (a != null) pairs.add((user: m.body, assistant: a.body));
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
        budget: budget,
        spent: total.spent,
        reserved: total.held,
        keyRemaining: null,
      );
      return [
        interpolate(t('estimate.input'), {'count': plan.prompt}),
        interpolate(t('estimate.reply'), {'count': plan.completion}),
        if (!c.free)
          plan.reserve == null
              ? t('estimate.cost_unknown')
              : interpolate(t('estimate.cost'), {
                  'amount': '${plan.reserve} ${c.service.currency}',
                }),
      ].join(' · ');
    } on PlanRejected {
      return t('estimate.over_limit');
    }
  }

  Future<void> toggleConfirmations(ChatRecord c, bool enabled) async {
    if (c.free) return;
    final key = c.id, rev = settings['connection_rev'];
    if (enabled &&
        !await confirm(
          context,
          t('paid.no_confirmation'),
          t('paid.no_confirmation_help'),
          t('common.cancel'),
          t('chat.save'),
        )) {
      return;
    }
    if (!alive || key != selected) return;
    final n = await store.db.rawUpdate(
      'UPDATE chats SET skip_paid=?,connection_rev=connection_rev+1 WHERE id=? AND connection_rev=?',
      [enabled ? 1 : 0, key, rev],
    );
    if (n != 1) throw const PlanRejected('connection.stale');
    widget.session.sending.invalidate();
    await load();
  }

  Widget editor(ChatRecord c, List<JournalRow> local, BudgetTotal total) {
    final canSend =
        !sending && !total.blocked && composer.text.trim().isNotEmpty;
    final short =
        MediaQuery.sizeOf(context).height -
            MediaQuery.viewInsetsOf(context).bottom <
        430;
    return ColoredBox(
      color: panel,
      child: Padding(
        padding: EdgeInsets.all(short ? 4 : 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Expanded(
                  child: Focus(
                    onKeyEvent: (_, event) {
                      if (event is KeyDownEvent &&
                          (event.logicalKey == LogicalKeyboardKey.enter ||
                              event.logicalKey ==
                                  LogicalKeyboardKey.numpadEnter) &&
                          !HardwareKeyboard.instance.isShiftPressed) {
                        if (canSend) unawaited(run(send));
                        return KeyEventResult.handled;
                      }
                      return KeyEventResult.ignored;
                    },
                    child: TextField(
                      controller: composer,
                      minLines: 1,
                      maxLines: short ? 2 : 5,
                      keyboardType: TextInputType.multiline,
                      textInputAction: TextInputAction.send,
                      onSubmitted: (_) {
                        if (canSend) unawaited(run(send));
                      },
                      decoration: InputDecoration(
                        labelText: t('composer.message'),
                        hintText: t('composer.hint'),
                      ),
                      onChanged: (_) {
                        widget.session.sending.invalidate();
                        update();
                        unawaited(run(editText));
                      },
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                FilledButton.icon(
                  onPressed: canSend ? () => run(send) : null,
                  icon: const Icon(Icons.send),
                  label: Text(t('composer.send')),
                ),
              ],
            ),
            if (!short)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Tooltip(
                  message: t('estimate.help'),
                  child: Text(
                    estimate(c, local),
                    style: const TextStyle(color: muted, fontSize: 12),
                  ),
                ),
              ),
            if (sending) const LinearProgressIndicator(),
          ],
        ),
      ),
    );
  }

  Widget conversation(bool wide) {
    final c = chat, local = rows.where((r) => r['chat'] == selected).toList();
    final total = c == null ? null : totals(local, c.service);
    return LayoutBuilder(
      builder: (context, constraints) {
        final short = constraints.maxHeight < 480;
        final scrollTogether =
            short || MediaQuery.textScalerOf(context).scale(16) > 20;
        final head = <Widget>[
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8),
            child: Row(
              children: [
                IconButton(
                  onPressed: () => setState(() => showChats = !showChats),
                  icon: const Icon(Icons.menu),
                  tooltip: t('chat.open_list'),
                ),
                Expanded(
                  child: Text(
                    c?.title ?? 'Tokenlogue',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      fontSize: 20,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
                IconButton(
                  onPressed: () => run(() => newChat()),
                  icon: const Icon(Icons.add),
                  tooltip: t('chat.untitled'),
                ),
                IconButton(
                  onPressed: widget.onLock,
                  icon: const Icon(Icons.lock_outline),
                  tooltip: t('chat.lock'),
                ),
                IconButton(
                  onPressed: () => run(protection),
                  icon: const Icon(Icons.shield_outlined, color: Colors.amber),
                  tooltip: t('protection_panel.open'),
                ),
                IconButton(
                  onPressed: () => run(menu),
                  icon: const Icon(Icons.more_vert),
                  tooltip: t('chat.options'),
                ),
              ],
            ),
          ),
          if (c != null)
            Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
              child: Text(
                interpolate(t('workspace.current_model'), {
                  'provider': c.service.label,
                  'model': c.model == ModelChoice.router.id
                      ? t('model.free_router')
                      : c.model,
                }),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(color: muted, fontSize: 12),
              ),
            ),
          if (c != null) ...[
            if (!short)
              Align(
                alignment: Alignment.centerLeft,
                child: Wrap(
                  children: [
                    TextButton.icon(
                      onPressed: () => run(rename),
                      icon: const Icon(Icons.edit_outlined),
                      label: Text(t('chat.rename')),
                    ),
                    TextButton.icon(
                      style: TextButton.styleFrom(
                        foregroundColor: Colors.redAccent,
                      ),
                      onPressed: () => run(remove),
                      icon: const Icon(Icons.delete_outline),
                      label: Text(t('chat.delete_chat')),
                    ),
                  ],
                ),
              ),
            if (!short) const SizedBox(height: 8),
            Container(
              width: double.infinity,
              color: panel,
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
              child: Wrap(
                spacing: 10,
                runSpacing: 4,
                children: [
                  Text(
                    c.free
                        ? interpolate(t('metrics.free_summary'), {
                            'count':
                                (settings['token_limit'] as int? ?? 8192) -
                                total!.used -
                                total.reserved,
                            'last': local.lastOrNull?['usage_total'] ?? '—',
                          })
                        : interpolate(t('metrics.paid_summary'), {
                            'amount': budget == null
                                ? '—'
                                : '${budget! - total!.spent - total.held} ${c.service.currency}',
                            'last': local.lastOrNull?['cost'] ?? '—',
                          }),
                  ),
                  Tooltip(
                    message: interpolate(t('metrics.account_help'), {
                      'provider': c.service.label,
                    }),
                    child: Text(
                      accountText(c.service),
                      style: const TextStyle(fontSize: 12, color: muted),
                    ),
                  ),
                  if (!c.free && c.service == Service.openrouter)
                    Text(
                      keyLimitText(c.service),
                      style: const TextStyle(fontSize: 12, color: muted),
                    ),
                  if (!c.free)
                    FilterChip(
                      selected: settings['skip_paid'] == 1,
                      label: Text(t('metrics.without_confirmation')),
                      onSelected: (enabled) =>
                          run(() => toggleConfirmations(c, enabled)),
                    ),
                ],
              ),
            ),
          ],
          if (error.isNotEmpty)
            Text(error, style: const TextStyle(color: Colors.amber)),
        ];
        final history = c == null
            ? Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(t('chat.empty')),
                    Text(t('chat.create_help')),
                    FilledButton(
                      onPressed: () => run(() => newChat()),
                      child: Text(t('chat.untitled')),
                    ),
                  ],
                ),
              )
            : ListView(
                primary: false,
                shrinkWrap: scrollTogether,
                physics: scrollTogether
                    ? const NeverScrollableScrollPhysics()
                    : null,
                padding: const EdgeInsets.all(16),
                children: [
                  if (messages.isEmpty) Text(t('history.empty')),
                  for (final m in messages)
                    Card(
                      color: m.role == 'user' ? elevated : panel,
                      child: Padding(
                        padding: const EdgeInsets.all(16),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                Expanded(
                                  child: Text(
                                    m.role == 'user'
                                        ? t('protection_panel.you')
                                        : 'Tokenlogue',
                                  ),
                                ),
                                IconButton(
                                  onPressed: () => Clipboard.setData(
                                    ClipboardData(text: m.body),
                                  ),
                                  icon: const Icon(Icons.copy),
                                  tooltip: t('protection_panel.copy_message'),
                                ),
                              ],
                            ),
                            MessageBody(
                              source: m.body,
                              copyLabel: t('protection_panel.copy_code'),
                            ),
                          ],
                        ),
                      ),
                    ),
                  for (final a in local)
                    if (['unknown', 'unknownCost'].contains(a['state']))
                      TextButton(
                        onPressed: () => run(() => release(a['id'] as String)),
                        child: Text(t('reserve.release_unknown')),
                      )
                    else if (a['state'] == 'failed')
                      TextButton(
                        onPressed: sending
                            ? null
                            : () => run(
                                () => send(retry: a['turn_id'] as String),
                              ),
                        child: Text(t('common.retry')),
                      ),
                ],
              );
        final foot = <Widget>[
          if (c != null) editor(c, local, total!),
          if (!short)
            Text(
              t('chat.history_warning'),
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 12, color: muted),
            ),
        ];
        if (scrollTogether) {
          return ListView(
            padding: EdgeInsets.zero,
            children: [...head, history, ...foot],
          );
        }
        return Column(
          children: [
            ...head,
            Expanded(child: history),
            ...foot,
          ],
        );
      },
    );
  }

  @override
  void dispose() {
    accounts.dispose();
    composer.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final wide = MediaQuery.sizeOf(context).width >= 760;
    final home = Row(
      children: [
        if (wide && !showChats) SizedBox(width: 320, child: list()),
        Expanded(child: !wide && showChats ? list() : conversation(wide)),
      ],
    );
    return PopScope(
      canPop: page == 0 && !showChats,
      onPopInvokedWithResult: (didPop, _) {
        if (didPop) return;
        if (page != 0) {
          unawaited(selectPage(0));
        } else {
          setState(() => showChats = false);
        }
      },
      child: Scaffold(
        body: SafeArea(
          bottom: false,
          child: loading
              ? const Center(child: CircularProgressIndicator())
              : IndexedStack(
                  index: page,
                  children: [
                    home,
                    ProviderPage(
                      key: ValueKey(providerFilter),
                      t: t,
                      vault: widget.vault,
                      profile: widget.session.profile,
                      api: widget.api,
                      accounts: accounts,
                      policy: policy,
                      initial: providerFilter,
                      setPolicy: (v) {
                        setState(() => policy = v);
                        unawaited(
                          run(() => store.setPreference('new_provider', v)),
                        );
                      },
                      onKeyChanged: (_) => widget.session.sending.invalidate(),
                    ),
                    AnalyticsPage(
                      key: const ValueKey('tokens'),
                      t: t,
                      rows: rows,
                      money: false,
                    ),
                    AnalyticsPage(
                      key: const ValueKey('spending'),
                      t: t,
                      rows: rows,
                      money: true,
                    ),
                  ],
                ),
        ),
        bottomNavigationBar: DecoratedBox(
          decoration: const BoxDecoration(
            color: pageBackground,
            border: Border(top: BorderSide(color: border)),
          ),
          child: SafeArea(
            top: false,
            child: NavigationBar(
              backgroundColor: pageBackground,
              indicatorColor: primary,
              selectedIndex: page,
              onDestinationSelected: (i) => run(() => selectPage(i)),
              destinations: [
                for (final (name, icon) in [
                  ('nav.home', Icons.home_outlined),
                  ('providers.title', Icons.key_outlined),
                  ('nav.tokens', Icons.bar_chart_outlined),
                  ('nav.spending', Icons.payments_outlined),
                ])
                  NavigationDestination(
                    icon: Icon(icon),
                    selectedIcon: Icon(icon, color: pageBackground),
                    label: t(name),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
