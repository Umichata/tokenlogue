[English](CHANGELOG.md#english) · [Русский](CHANGELOG.ru.md#russian)

<a id="english"></a>
<a id="lang-en"></a>

# Release notes

## 0.1.1

**Local release.** Version 0.1.1 has not been published. The [published 0.1.0 Preview](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-preview.a981db9) remains available separately.

### Changes from 0.1.0

- Separate OpenRouter and VSEGPT forms with a compact **Provider** dropdown for viewing.
- Daily token charts separate API usage, estimates and incomplete or undated data.
- **Choose each time** selects a provider for each new chat while retaining existing service preferences.
- Catalogue failures show a specific safe cause and support refreshing the list. VSEGPT opens paid models directly, without a separate mode step.
- Saved-key checks are available on the OpenRouter mode screen and VSEGPT model list. They update the current status without re-entering a key or generating a message.
- Provider-aware model choices and saved filters on **Tokens** and **Spending**.
- Independent USD and RUB panels and protection against stale statistics replacing the current view.
- Shorter English and Russian messages for keys, balances and errors.
- Clear labels for service balance, OpenRouter key limit and local chat budget. VSEGPT does not display an unsupported separate key limit.
- A chat connection block with its provider, a safe shared-key mask and provider-specific settings.
- Explicit provider changes for an existing chat, with model and budget review while preserving history and draft.
- Shared token accounting, separate provider money states and historical request identities across provider changes. Changing provider revokes earlier permission for automatic paid sends.
- Updated guides and examples of the four-page interface.

The [user guide](docs/user-guide.md), [provider guide](docs/providers.md) and [statistics guide](docs/analytics.md) explain the workflow. Demonstration illustrations do not prove live provider requests.

### Updating

Install a compatible Android APK over the existing app with the same signing certificate. Keep application data. On Linux, close older copies and retain access to the same system key store. Review [data protection](docs/security.md) before moving a profile.

### Limits

Local token and cost estimates are approximate. A balance can be unavailable even when a key works for chat. Native ARM64 operation with a 16 KiB kernel remains untested. Some native dependency source-to-binary links remain incomplete. See [source materials](docs/source-materials.md).
