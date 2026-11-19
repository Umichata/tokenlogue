import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:sqflite/sqflite.dart';
import 'data/chat_store.dart';
import 'data/providers.dart';
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

enum Screen { loading, key, setup, pin, home, error }

class _TokenlogueState extends State<Tokenlogue> with WidgetsBindingObserver {
  final vault = ProfileVault(), api = ProviderApi();
  final keyField = TextEditingController(),
      pinField = TextEditingController(),
      repeat = TextEditingController();
  final words = <String, Map<String, dynamic>>{};
  String lang = 'ru', notice = '', pendingKey = '';
  bool busy = false, verified = false, offerUnverified = false;
  int epoch = 0;
  Screen screen = Screen.loading;
  UnlockedProfile? profile;
  ChatStore? store;

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
      final existing = await vault.exists();
      if (!existing && await databaseExists(await ChatStore.location())) {
        throw StateError('missing_binding');
      }
      if (mounted) setState(() => screen = existing ? Screen.pin : Screen.key);
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
    profile?.dispose();
    profile = null;
    final previous = store;
    store = null;
    previous?.db.close();
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
        if (screen == Screen.home) screen = Screen.pin;
        if (screen == Screen.setup) screen = Screen.key;
      });
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    profile?.dispose();
    store?.db.close();
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
        offerUnverified = s == Service.vsegpt && result == KeyStatus.unverified;
      }
    });
  }

  Future<void> authenticate() async {
    if (busy || !validPin(pinField.text)) return;
    final creating = screen == Screen.setup;
    if (creating && pinField.text != repeat.text) return;
    final current = epoch, pin = pinField.text;
    setState(() {
      busy = true;
      notice = '';
    });
    try {
      if (creating) await vault.register(pin, pendingKey, verified);
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
      final opened = await ChatStore.open(unlocked);
      if (epoch != current || !mounted) {
        await opened.db.close();
        unlocked.dispose();
        return;
      }
      profile = unlocked;
      store = opened;
      pendingKey = '';
      pinField.clear();
      repeat.clear();
      setState(() => screen = Screen.home);
    } on PinLocked catch (_) {
      if (epoch == current) setState(() => notice = 'auth.enter_pin');
    } catch (_) {
      if (epoch == current) setState(() => screen = Screen.error);
    } finally {
      if (mounted && epoch == current) setState(() => busy = false);
    }
  }

  Widget password(
    TextEditingController c,
    String label, {
    bool numeric = false,
    bool focus = false,
  }) => TextField(
    controller: c,
    autofocus: focus,
    obscureText: true,
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
            style: TextStyle(fontSize: 22, fontWeight: FontWeight.w500),
          ),
        ),
        DropdownButton<String>(
          value: lang,
          items: const [
            DropdownMenuItem(value: 'en', child: Text('EN')),
            DropdownMenuItem(value: 'ru', child: Text('RU')),
          ],
          onChanged: (s) {
            if (s != null) setState(() => lang = s);
          },
        ),
      ],
    ),
  );
  List<Widget> fields() {
    if (screen == Screen.key) {
      final service = Service.detect(keyField.text);
      return [
        Text(t('providers.title'), style: const TextStyle(fontSize: 28)),
        Text(
          t('providers.setup_description'),
          style: const TextStyle(color: muted),
        ),
        password(keyField, t('providers.key'), focus: true),
        Text(
          service == null
              ? t('providers.enter_key')
              : t('providers.detected').replaceAll('{provider}', service.label),
          style: const TextStyle(color: muted),
        ),
        if (notice.isNotEmpty) Text(t(notice)),
        if (busy) const LinearProgressIndicator(),
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
    final creating = screen == Screen.setup;
    return [
      Text(
        t(creating ? 'auth.choose_pin' : 'auth.sign_in'),
        style: const TextStyle(fontSize: 28),
      ),
      Text(
        t(creating ? 'auth.pin_instructions' : 'auth.enter_pin'),
        style: const TextStyle(color: muted),
      ),
      password(pinField, 'PIN', numeric: true),
      if (creating) password(repeat, t('auth.repeat_pin'), numeric: true),
      if (notice.isNotEmpty) Text(t(notice)),
      if (busy) const LinearProgressIndicator(),
      FilledButton(
        onPressed:
            busy ||
                !validPin(pinField.text) ||
                (creating && repeat.text != pinField.text)
            ? null
            : authenticate,
        child: Text(t(creating ? 'auth.save_pin' : 'auth.sign_in')),
      ),
    ];
  }

  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'Tokenlogue Dart',
    theme: buildTheme(),
    debugShowCheckedModeBanner: false,
    home: Scaffold(
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
                Screen.home => Center(
                  child: IconButton(
                    onPressed: lock,
                    icon: const Icon(Icons.lock),
                    tooltip: t('auth.lock'),
                  ),
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
                          crossAxisAlignment: CrossAxisAlignment.stretch,
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
  );
}
