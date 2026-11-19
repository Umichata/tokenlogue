import 'dart:async';
import 'dart:convert';
import 'dart:math';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:sqflite/sqflite.dart';
import 'data/chat_store.dart';
import 'data/providers.dart';
import 'data/session.dart';
import 'presentation/controls.dart';
import 'presentation/workspace.dart';
import 'data/vault.dart';
import 'domain/provider.dart';
import 'presentation/theme.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const Tokenlogue());
}

class Tokenlogue extends StatefulWidget {
  const Tokenlogue({super.key});
  @override
  State<Tokenlogue> createState() => _TokenlogueState();
}

enum Screen {
  loading,
  key,
  setup,
  pin,
  home,
  recovery,
  recovered,
  deletion,
  error,
}

class _TokenlogueState extends State<Tokenlogue> with WidgetsBindingObserver {
  final vault = ProfileVault(), api = ProviderApi();
  final keyField = TextEditingController(),
      pinField = TextEditingController(),
      repeat = TextEditingController();
  final words = <String, Map<String, dynamic>>{};
  String lang = 'ru', notice = '', pendingKey = '';
  bool busy = false, verified = false, offerUnverified = false;
  final _revealedPins = <TextEditingController>{};
  int epoch = 0;
  Screen screen = Screen.loading;
  UnlockedProfile? profile;
  Session? session;
  Future<void> closing = Future.value();
  final deletion = TextEditingController();
  bool deviceRecovery = false, deletePending = false;
  Timer? cooldown;
  int remainingSeconds = 0, attemptsRemaining = 3;
  Screen deletionOrigin = Screen.pin;

  String t(String key) => words[lang]?[key] as String? ?? key;
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    initialize();
  }

  Future<void> initialize() async {
    try {
      for (final l in ['en', 'ru']) {
        words[l] =
            jsonDecode(await rootBundle.loadString('assets/locales/$l.json'))
                as Map<String, dynamic>;
      }
      lang =
          await ProfileVault.channel.invokeMethod<String>('language') ?? 'ru';
      deviceRecovery = await vault.canRecover();
      if (await ProfileVault.channel.invokeMethod<bool>('deleting') == true) {
        deletePending = true;
        await finishDeletion();
      }
      final existing = await vault.exists();
      if (!existing && await databaseExists(await ChatStore.location())) {
        throw StateError('missing_binding');
      }
      if (mounted) setState(() => screen = existing ? Screen.pin : Screen.key);
      if (existing && mounted) {
        final ms = await vault.readCooldown();
        if (ms > 0 && mounted) showCooldown(ms);
      }
    } catch (_) {
      if (mounted) setState(() => screen = Screen.error);
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.hidden ||
        state == AppLifecycleState.paused) {
      lock();
    }
  }

  void lock() {
    epoch++;
    vault.revokeRecovery();
    if (session != null) closing = session!.close();
    profile = null;
    session = null;
    deletion.clear();
    _revealedPins.clear();

    keyField.clear();
    pinField.clear();
    repeat.clear();
    pendingKey = '';
    notice = '';
    busy = false;
    verified = false;
    offerUnverified = false;
    if (mounted) {
      setState(() {
        if ([
          Screen.home,
          Screen.recovery,
          Screen.recovered,
          if (!deletePending) Screen.deletion,
        ].contains(screen)) {
          screen = Screen.pin;
        }
        if (screen == Screen.setup) screen = Screen.key;
      });
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    vault.revokeRecovery();
    session?.close();
    cooldown?.cancel();
    deletion.dispose();
    keyField.dispose();
    pinField.dispose();
    repeat.dispose();
    super.dispose();
  }

  Future<void> check() async {
    final value = keyField.text.trim(), s = Service.detect(keyField.text);
    if (s == null || busy) return;
    final current = epoch;
    setState(() {
      busy = true;
      notice = '';
      offerUnverified = false;
    });
    final result = await api.check(s, value);
    if (!mounted || epoch != current || value != keyField.text.trim()) return;
    setState(() {
      busy = false;
      if (result == KeyStatus.accepted) {
        verified = true;
        pendingKey = value;
        keyField.clear();
        screen = Screen.setup;
      } else {
        notice = result == KeyStatus.unverified
            ? 'providers.unverified_help'
            : 'providers.check_failed';
        offerUnverified =
            s == Service.vsegpt &&
            {
              KeyStatus.unverified,
              KeyStatus.unavailable,
              KeyStatus.limited,
            }.contains(result);
      }
    });
  }

  Future<void> authenticate() async {
    if (busy || !validPin(pinField.text)) return;
    final creating = screen == Screen.setup || screen == Screen.recovered;
    if (creating && pinField.text != repeat.text) return;
    final current = epoch, pin = pinField.text;
    setState(() {
      busy = true;
      notice = '';
    });
    try {
      await closing;
      if (epoch != current) return;
      if (screen == Screen.setup) {
        await vault.register(pin, pendingKey, verified);
      }
      if (screen == Screen.recovered && !await vault.replacePin(pin)) {
        if (epoch == current) {
          setState(() {
            screen = Screen.pin;
            notice = 'recovery.expired';
          });
        }
        return;
      }
      if (epoch != current) {
        if (creating && mounted) setState(() => screen = Screen.pin);
        return;
      }
      final unlocked = await vault.unlock(pin);
      if (epoch != current || !mounted) {
        unlocked?.dispose();
        return;
      }
      if (unlocked == null) {
        setState(() => notice = 'auth.pin_mismatch');
        return;
      }
      if (!await databaseExists(await ChatStore.location()) &&
          !unlocked.creating) {
        unlocked.dispose();
        throw StateError('missing_database');
      }
      final opened = await ChatStore.open(unlocked);
      if (unlocked.creating) await vault.markReady(unlocked);
      if (epoch != current || !mounted) {
        await opened.db.close();
        unlocked.dispose();
        return;
      }
      cooldown?.cancel();
      remainingSeconds = 0;
      profile = unlocked;
      session = Session(unlocked, opened, api);
      pendingKey = '';
      pinField.clear();
      repeat.clear();
      setState(() => screen = Screen.home);
    } on PinRejected catch (e) {
      if (epoch == current) {
        setState(() {
          attemptsRemaining = e.remaining;
          notice = 'auth.pin_attempts_remaining';
          pinField.clear();
        });
      }
    } on PinLocked catch (e) {
      if (epoch == current) showCooldown(e.milliseconds);
    } catch (_) {
      if (epoch == current) setState(() => screen = Screen.error);
    } finally {
      if (mounted && epoch == current) setState(() => busy = false);
    }
  }

  void showCooldown(int ms) {
    cooldown?.cancel();
    final timer = Stopwatch()..start();
    setState(() {
      remainingSeconds = (ms + 999) ~/ 1000;
      notice = 'auth.lock_countdown';
      pinField.clear();
    });
    cooldown = Timer.periodic(const Duration(milliseconds: 250), (tick) {
      if (!mounted) {
        tick.cancel();
        return;
      }
      final left = ((ms - timer.elapsedMilliseconds + 999) ~/ 1000).clamp(
        0,
        300,
      );
      if (left == remainingSeconds) return;
      setState(() {
        remainingSeconds = left;
        if (left == 0) {
          tick.cancel();
          notice = 'auth.lock_expired';
        }
      });
    });
  }

  Future<void> setLanguage(String next) async {
    if (next != 'en' && next != 'ru') return;
    await ProfileVault.channel.invokeMethod<void>('setLanguage', next);
    if (mounted) setState(() => lang = next);
  }

  Future<void> startRecovery() async {
    final g = epoch;
    setState(() {
      busy = true;
      notice = '';
    });
    try {
      final ok = await vault.requestRecovery(t('recovery.explanation'));
      if (!mounted || g != epoch || screen != Screen.recovery) return;
      FocusManager.instance.primaryFocus?.unfocus();
      pinField.clear();
      repeat.clear();
      setState(() {
        screen = ok ? Screen.recovered : Screen.pin;
        notice = ok ? 'recovery.verified_notice' : 'recovery.cancelled';
      });
    } on TimeoutException {
      if (mounted && epoch == g) {
        setState(() {
          screen = Screen.pin;
          notice = 'recovery.expired';
        });
      }
    } catch (_) {
      if (mounted && g == epoch) {
        setState(() {
          screen = Screen.pin;
          notice = 'recovery.failed';
        });
      }
    } finally {
      if (mounted && g == epoch) setState(() => busy = false);
    }
  }

  void cancelRecovery() {
    epoch++;
    vault.revokeRecovery();
    pinField.clear();
    repeat.clear();
    setState(() {
      screen = Screen.pin;
      notice = 'recovery.cancelled';
      busy = false;
    });
  }

  void askDelete() {
    deletionOrigin = screen;
    deletion.clear();
    setState(() => screen = Screen.deletion);
  }

  Future<void> finishDeletion() async {
    await closing;
    await deleteDatabase(await ChatStore.location());
    await ProfileVault.channel.invokeMethod<void>('finishDelete');
    deletePending = false;
  }

  Future<void> deleteProfile() async {
    if (busy ||
        !deletePending && deletion.text != t('profile_deletion.phrase')) {
      return;
    }
    lock();
    setState(() {
      busy = true;
      screen = Screen.deletion;
    });
    try {
      await ProfileVault.channel.invokeMethod<void>('beginDelete');
      deletePending = true;
      await finishDeletion();
      if (mounted) {
        setState(() {
          screen = Screen.key;
          notice = 'profile_deletion.success';
        });
      }
    } catch (_) {
      if (mounted) setState(() => notice = 'profile_deletion.unavailable');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  String statusText() => switch (notice) {
    'auth.lock_countdown' => interpolate(t(notice), {
      'time':
          '${(remainingSeconds ~/ 60).toString().padLeft(2, "0")}:${(remainingSeconds % 60).toString().padLeft(2, "0")}',
    }),
    'auth.pin_attempts_remaining' => interpolate(t(notice), {
      'remaining': attemptsRemaining,
    }),
    _ => t(notice),
  };

  Widget password(
    TextEditingController c,
    String label, {
    bool numeric = false,
    bool focus = false,
  }) => TextField(
    controller: c,
    autofocus: focus,
    obscureText: !_revealedPins.contains(c),
    enabled: !busy,
    autocorrect: false,
    enableSuggestions: false,
    enableIMEPersonalizedLearning: false,
    keyboardType: numeric
        ? TextInputType.number
        : TextInputType.visiblePassword,
    maxLength: numeric ? 4 : null,
    inputFormatters: numeric
        ? [FilteringTextInputFormatter.allow(RegExp('[0-9]'))]
        : null,
    decoration: InputDecoration(
      labelText: label,
      hintText: numeric ? null : t('providers.key_hint'),
      suffixIcon: IconButton(
        tooltip: t(
          _revealedPins.contains(c) ? 'providers.conceal' : 'providers.reveal',
        ),
        icon: Icon(
          _revealedPins.contains(c) ? Icons.visibility_off : Icons.visibility,
        ),
        onPressed: () => setState(() {
          if (!_revealedPins.add(c)) _revealedPins.remove(c);
        }),
      ),
    ),
    onChanged: (_) => setState(() {
      notice = '';
      offerUnverified = false;
    }),
  );
  Widget header() => Container(
    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
    decoration: const BoxDecoration(
      border: Border(bottom: BorderSide(color: border)),
    ),
    child: Row(
      children: [
        Image.asset(
          'assets/branding/tokenlogue-logo-transparent.png',
          width: 32,
          height: 32,
        ),
        const SizedBox(width: 10),
        const Expanded(
          child: Text(
            'Tokenlogue',
            style: TextStyle(fontSize: 20, fontWeight: FontWeight.w600),
          ),
        ),
        DropdownMenu<String>(
          width: 104,
          menuHeight: 176,
          initialSelection: lang,
          textStyle: const TextStyle(fontSize: 13, color: ink),
          label: Text(
            t('language.label'),
            style: const TextStyle(fontSize: 11, color: muted),
          ),
          inputDecorationTheme: InputDecorationTheme(
            isDense: true,
            contentPadding: const EdgeInsets.symmetric(
              horizontal: 12,
              vertical: 8,
            ),
            enabledBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(10),
              borderSide: const BorderSide(color: border),
            ),
          ),
          dropdownMenuEntries: const [
            DropdownMenuEntry(value: 'ru', label: 'RU'),
            DropdownMenuEntry(value: 'en', label: 'EN'),
          ],
          onSelected: (v) {
            if (v != null) setLanguage(v);
          },
        ),
      ],
    ),
  );
  List<Widget> fields() {
    if (screen == Screen.key) {
      final service = Service.detect(keyField.text);
      return [
        Text(
          t('providers.title'),
          style: const TextStyle(
            fontSize: 26,
            fontWeight: FontWeight.w600,
            height: 1.2,
          ),
        ),
        Text(
          t('providers.setup_description'),
          style: const TextStyle(color: muted),
        ),
        SecretField(
          controller: keyField,
          label: t('providers.key'),
          hint: t('providers.key_hint'),
          t: t,
          focus: true,
          enabled: !busy,
          changed: (_) => setState(() {
            offerUnverified = false;
            notice = '';
          }),
        ),
        Text(
          service == null
              ? t('providers.enter_key')
              : t('providers.detected').replaceAll('{provider}', service.label),
          style: const TextStyle(color: muted),
        ),
        if (notice.isNotEmpty) Text(statusText()),
        if (busy) const BrandLoader() else const SizedBox.shrink(),
        FilledButton.icon(
          onPressed: busy || service == null ? null : check,
          icon: const Icon(Icons.verified_user),
          label: Text(t('auth.check_key')),
        ),
        if (offerUnverified)
          TextButton(
            onPressed: () {
              setState(() {
                pendingKey = keyField.text.trim();
                verified = false;
                keyField.clear();
                notice = '';
                screen = Screen.setup;
              });
            },
            child: Text(t('providers.save_unverified')),
          ),
      ];
    }
    if (screen == Screen.deletion) {
      return [
        Text(
          t('profile_deletion.title'),
          style: const TextStyle(
            fontSize: 26,
            fontWeight: FontWeight.w600,
            height: 1.2,
          ),
        ),
        Text(t('profile_deletion.description')),
        Text(t('profile_deletion.remote_notice')),
        Text(t('profile_deletion.backup_notice')),
        if (!deletePending) ...[
          SelectableText(t('profile_deletion.phrase')),
          TextField(
            controller: deletion,
            decoration: InputDecoration(
              labelText: t('profile_deletion.phrase_prompt'),
            ),
            onChanged: (_) => setState(() {}),
          ),
        ],
        if (notice.isNotEmpty) Text(statusText()),
        FilledButton(
          onPressed:
              !busy &&
                  (deletePending ||
                      deletion.text == t('profile_deletion.phrase'))
              ? deleteProfile
              : null,
          child: Text(
            t(
              deletePending
                  ? 'profile_deletion.retry'
                  : 'profile_deletion.confirm',
            ),
          ),
        ),
        if (!deletePending)
          TextButton(
            onPressed: busy
                ? null
                : () => setState(() => screen = deletionOrigin),
            child: Text(t('profile_deletion.cancel')),
          ),
      ];
    }
    if (screen == Screen.recovery) {
      return [
        Text(t('recovery.explanation')),
        FilledButton(
          onPressed: busy || !deviceRecovery ? null : startRecovery,
          child: Text(t('recovery.confirm_device')),
        ),
        TextButton(
          onPressed: cancelRecovery,
          child: Text(t('recovery.cancel')),
        ),
      ];
    }
    final creating = screen == Screen.setup || screen == Screen.recovered;
    return [
      Text(
        t(
          screen == Screen.recovered
              ? 'recovery.choose_new_pin'
              : creating
              ? 'auth.choose_pin'
              : 'auth.sign_in',
        ),
        style: const TextStyle(
          fontSize: 26,
          fontWeight: FontWeight.w600,
          height: 1.2,
        ),
      ),
      Text(
        t(creating ? 'auth.pin_instructions' : 'auth.enter_pin'),
        style: const TextStyle(color: muted),
      ),
      password(pinField, 'PIN', numeric: true),
      if (creating)
        TextButton.icon(
          onPressed: busy
              ? null
              : () {
                  final v = Random.secure()
                      .nextInt(10000)
                      .toString()
                      .padLeft(4, '0');
                  setState(() {
                    pinField.text = v;
                    repeat.clear();
                  });
                },
          icon: const Icon(Icons.casino_outlined),
          label: Text(t('auth.suggest_pin')),
        ),
      if (creating) password(repeat, t('auth.repeat_pin'), numeric: true),
      if (notice.isNotEmpty) Text(statusText()),
      if (busy) const BrandLoader(),
      FilledButton(
        onPressed:
            busy ||
                (remainingSeconds > 0 && screen == Screen.pin) ||
                !validPin(pinField.text) ||
                (creating && repeat.text != pinField.text)
            ? null
            : authenticate,
        child: Text(
          t(
            screen == Screen.recovered
                ? 'recovery.save_new_pin'
                : creating
                ? 'auth.save_pin'
                : 'auth.sign_in',
          ),
        ),
      ),
      if (screen == Screen.recovered)
        TextButton(
          onPressed: cancelRecovery,
          child: Text(t('recovery.cancel')),
        ),
      if (screen == Screen.pin) ...[
        TextButton(
          onPressed: () => setState(() {
            screen = Screen.recovery;
            notice = '';
          }),
          child: Text(t('recovery.forgot_pin')),
        ),
        if (!deviceRecovery) Text(t('recovery.unavailable')),
        TextButton(
          onPressed: askDelete,
          child: Text(t('profile_deletion.entry')),
        ),
      ],
      if (screen == Screen.setup)
        TextButton(
          onPressed: () {
            pendingKey = '';
            pinField.clear();
            repeat.clear();
            setState(() => screen = Screen.key);
          },
          child: Text(t('common.back')),
        ),
    ];
  }

  @override
  Widget build(BuildContext context) => MaterialApp(
    key: ValueKey((epoch, screen == Screen.home)),
    title: 'Tokenlogue Dart',
    theme: buildTheme(),
    debugShowCheckedModeBanner: false,
    home: Semantics(
      container: true,
      explicitChildNodes: true,
      identifier: 'tokenlogue.screen.${screen.name}',
      child: screen == Screen.home && session != null
          ? Workspace(
              session: session!,
              api: api,
              vault: vault,
              t: t,
              onLock: lock,
              onDelete: askDelete,
              language: lang,
              setLanguage: setLanguage,
            )
          : Scaffold(
              body: SafeArea(
                child: Column(
                  children: [
                    header(),
                    Expanded(
                      child: switch (screen) {
                        Screen.loading => const Center(
                          child: CircularProgressIndicator(),
                        ),
                        Screen.error => Center(
                          child: Text(t('service.key_save_failed')),
                        ),
                        _ => ListView(
                          padding: const EdgeInsets.fromLTRB(16, 24, 16, 32),
                          children: [
                            Align(
                              alignment: Alignment.topCenter,
                              child: Container(
                                width: 420,
                                padding: const EdgeInsets.all(24),
                                decoration: BoxDecoration(
                                  color: panel,
                                  border: Border.all(color: border),
                                  borderRadius: BorderRadius.circular(16),
                                ),
                                child: Column(
                                  crossAxisAlignment:
                                      CrossAxisAlignment.stretch,
                                  spacing: 16,
                                  children: fields(),
                                ),
                              ),
                            ),
                          ],
                        ),
                      },
                    ),
                  ],
                ),
              ),
            ),
    ),
  );
}
