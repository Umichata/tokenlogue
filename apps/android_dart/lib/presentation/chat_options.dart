import 'package:flutter/material.dart';

import '../data/providers.dart';
import '../domain/provider.dart';
import 'controls.dart';
import 'provider_page.dart';
import 'theme.dart';

class ChatOptions extends StatelessWidget {
  const ChatOptions({
    super.key,
    required this.t,
    required this.language,
    required this.accounts,
    required this.service,
    required this.maskedKey,
    required this.verified,
    required this.paid,
    required this.skipConfirmation,
  });
  final Translate t;
  final String language;
  final AccountState accounts;
  final Service? service;
  final String? maskedKey;
  final bool verified, paid, skipConfirmation;

  Widget connection(BuildContext context, Service provider) {
    return ListenableBuilder(
      listenable: accounts,
      builder: (ctx, _) {
        final checked = accounts.keyChecks[provider];
        final accepted =
            checked == KeyStatus.accepted || (checked == null && verified);
        final color = maskedKey == null
            ? muted
            : accepted
            ? primary
            : Colors.amber;
        final status =
            checked == null ||
                checked == KeyStatus.accepted ||
                checked == KeyStatus.unverified
            ? interpolate(
                t(accepted ? 'metrics.key_valid' : 'metrics.key_unverified'),
                {'provider': provider.label},
              )
            : t(checked.message);
        final limit = provider == Service.openrouter
            ? accounts.routerLimits?.amount
            : null;
        final checking = accounts.loading.contains(provider);
        return Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: color.withValues(alpha: .12),
            borderRadius: BorderRadius.circular(16),
          ),
          child: Column(
            spacing: 6,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      t('connection.provider'),
                      style: const TextStyle(color: muted),
                    ),
                  ),
                  Text(provider.label),
                ],
              ),
              Text(
                maskedKey == null
                    ? t('connection.no_key')
                    : interpolate(t('connection.masked_key'), {
                        'provider': provider.label,
                        'mask': maskedKey,
                      }),
              ),
              if (maskedKey != null)
                Text(status, style: TextStyle(color: color)),
              if (limit != null)
                Text(
                  interpolate(t('providers.key_remaining'), {
                    'amount': limit.toString(),
                    'currency': provider.currency,
                  }),
                ),
              if (checking) const LinearProgressIndicator(),
              TextButton.icon(
                onPressed: maskedKey == null || checking
                    ? null
                    : () => accounts.refresh(provider),
                icon: const Icon(Icons.refresh),
                label: Text(t('key.refresh')),
              ),
              TextButton.icon(
                onPressed: () =>
                    Navigator.pop(context, 'connection.configure_key'),
                icon: const Icon(Icons.key),
                label: Text(
                  interpolate(t('connection.configure_key'), {
                    'provider': provider.label,
                  }),
                ),
              ),
              TextButton.icon(
                onPressed: () =>
                    Navigator.pop(context, 'connection.change_provider'),
                icon: const Icon(Icons.swap_horiz),
                label: Text(t('connection.change_provider')),
              ),
            ],
          ),
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final compact =
        MediaQuery.sizeOf(context).height -
            MediaQuery.viewInsetsOf(context).bottom <
        560;
    final actions = <Widget>[
      if (service case final provider?) ...[
        Text(
          t('connection.title'),
          style: const TextStyle(fontWeight: FontWeight.bold),
        ),
        connection(context, provider),
      ],
      const Divider(),
      Align(
        alignment: Alignment.centerLeft,
        child: SizedBox(
          width: 200,
          child: DropdownButtonFormField<String>(
            initialValue: language,
            decoration: InputDecoration(labelText: t('language.label')),
            items: const [
              DropdownMenuItem(value: 'en', child: Text('English')),
              DropdownMenuItem(value: 'ru', child: Text('Русский')),
            ],
            onChanged: (lang) {
              if (lang != null) {
                Navigator.pop(context, 'language.$lang');
              }
            },
          ),
        ),
      ),
      const Divider(),
      TextButton.icon(
        onPressed: () => Navigator.pop(context, 'protection_panel.open'),
        icon: const Icon(Icons.shield_outlined),
        label: Text(t('protection_panel.open')),
      ),
      if (service != null) ...[
        const Divider(),
        TextButton(
          onPressed: () => Navigator.pop(context, 'limits.dialog'),
          child: Text(t('limits.dialog')),
        ),
        if (paid)
          SwitchListTile(
            value: skipConfirmation,
            title: Text(t('metrics.without_confirmation')),
            onChanged: (_) => Navigator.pop(context, 'toggle_confirm'),
          ),
        if (compact)
          for (final op in ['chat.rename', 'chat.delete_chat'])
            TextButton(
              onPressed: () => Navigator.pop(context, op),
              child: Text(t(op)),
            ),
      ],
      TextButton(
        onPressed: () => Navigator.pop(context, 'profile_deletion.entry'),
        child: Text(t('profile_deletion.entry')),
      ),
    ];
    return Dialog(
      backgroundColor: panel,
      insetPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 24),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 480),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      t('chat.options'),
                      style: Theme.of(context).textTheme.titleLarge,
                    ),
                  ),
                  IconButton(
                    tooltip: t('common.cancel'),
                    onPressed: () => Navigator.pop(context),
                    icon: const Icon(Icons.close),
                  ),
                ],
              ),
              Flexible(
                child: SingleChildScrollView(
                  child: Column(
                    spacing: 10,
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: actions,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
