[English](CHANGELOG.md#english) · [Русский](CHANGELOG.ru.md#russian)

<a id="english"></a>
<a id="lang-en"></a>

# Release notes

## 0.1.1

[0.1.1 Preview](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.1-preview.1) is available for Android ARM64 and Linux x86_64. The earlier 0.1.0 Preview remains a separate release.

### Changes from 0.1.0

- Separate OpenRouter and VSEGPT forms with a compact **Provider** dropdown for viewing.
- Daily token charts separate API usage, estimates and incomplete or undated data.
- **Choose each time** selects a provider for each new chat while retaining existing service preferences.
- Catalogue failures show a specific safe cause and support refreshing the list. VSEGPT opens paid models directly, without a separate mode step.
- Mode and model screens scroll as one list so their actions remain reachable in short windows.
- Saved-key checks are available on the OpenRouter mode screen and VSEGPT model list. They update the current status without re-entering a key or generating a message.
- Provider-aware model choices and saved filters on **Tokens** and **Spending**.
- Independent USD and RUB panels and protection against stale statistics replacing the current view.
- Shorter English and Russian messages for keys, balances and errors.
- Clear labels for service balance, OpenRouter key limit and local chat budget. VSEGPT does not display an unsupported separate key limit.
- A chat connection block with its provider, a safe shared-key mask and provider-specific settings.
- Explicit provider changes for an existing chat, with model and budget review while preserving history and draft.
- Shared token accounting, separate provider money states and historical request identities across provider changes. Changing provider revokes earlier permission for automatic paid sends.
- Guidance on an open PIN form follows language changes without reopening it.
- A failed catalogue request during price confirmation is distinguished from a model confirmed absent from the catalogue. Failure does not send a message or discard the draft.
- Selected source-built native wheels have recorded sources, patches and recipes. CFFI libffi is identified separately from Python runtime libffi.
- Updated guides and examples of the four-page interface.

The [user guide](docs/user-guide.md), [provider guide](docs/providers.md) and [statistics guide](docs/analytics.md) explain the workflow. Demonstration illustrations do not prove live provider requests.

### Updating

Install a compatible Android APK over the existing app with the same signing certificate. Keep application data. On Linux, close older copies and retain access to the same system key store. Review [data protection](docs/security.md) before moving a profile.

### Limits

Local token and cost estimates are approximate. A balance can be unavailable even when a key works for chat. Native ARM64 operation with a 16 KiB kernel remains untested. The selected new native wheels have recorded sources and local builds. This does not retroactively establish the production of earlier wheels or claim complete independent reproducibility. See [source materials](docs/source-materials.md).
