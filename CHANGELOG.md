<a id="english"></a>
<a id="lang-en"></a>

<p align="left">
<a href="CHANGELOG.ru.md#russian" title="RU"><img align="right" src="docs/assets/ui/buttons/v3-en-10762eaa75fd.svg" alt="RU" width="46" height="30"></a> <a href="CHANGELOG.md#english" title="EN"><img align="right" src="docs/assets/ui/buttons/v3-en-2022af2877c8.svg" alt="EN" width="45" height="30"></a>
<a href="README.md" title="Home"><img src="docs/assets/ui/buttons/v3-en-4e7a793b89e3.svg" alt="Home" width="36" height="30"></a> <a href="https://github.com/Umichata/tokenlogue/tree/android" title="Android"><img src="docs/assets/ui/buttons/v3-en-4a0b64bd4ded.svg" alt="Android" width="83" height="30"></a> <a href="https://github.com/Umichata/tokenlogue/tree/linux" title="Linux"><img src="docs/assets/ui/buttons/v3-en-e31c456bd05c.svg" alt="Linux" width="65" height="30"></a>
</p>

<p align="center"><img src="docs/assets/tokenlogue-masthead-en-v3.svg" alt="Tokenlogue · OpenRouter + VSEGPT · Linux &amp; Android" width="100%"></p>

<p align="left"><a href="https://github.com/Umichata/tokenlogue/releases/tag/v0.1.1-preview.1" title="Downloads"><img src="docs/assets/ui/buttons/v3-en-126f5327c4ab.svg" alt="Downloads" width="105" height="30"></a> <a href="docs/README.md" title="Documentation map"><img src="docs/assets/ui/buttons/v3-en-2e9bcfa8f92e.svg" alt="Documentation map" width="173" height="30"></a> <a href="docs/user-guide.md" title="User guide"><img src="docs/assets/ui/buttons/v3-en-896461d1c049.svg" alt="User guide" width="104" height="30"></a> <a href="docs/providers.md" title="Providers"><img src="docs/assets/ui/buttons/v3-en-6aead91ab18a.svg" alt="Providers" width="95" height="30"></a> <a href="docs/analytics.md" title="Analytics"><img src="docs/assets/ui/buttons/v3-en-2a1d3373ceeb.svg" alt="Analytics" width="92" height="30"></a></p>

<a id="release-notes"></a>

# Release notes

<a id="011"></a>

## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> 0.1.1

[0.1.1 Preview](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.1-preview.1) is available for Android ARM64 and Linux x86_64. The earlier 0.1.0 Preview remains a separate release.

<a id="changes-from-010"></a>

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

<a id="updating"></a>

### Updating

Install a compatible Android APK over the existing app with the same signing certificate. Keep application data. On Linux, close older copies and retain access to the same system key store. Review [data protection](docs/security.md) before moving a profile.

<a id="limits"></a>

### Limits

Local token and cost estimates are approximate. A balance can be unavailable even when a key works for chat. Native ARM64 operation with a 16 KiB kernel remains untested. The selected new native wheels have recorded sources and local builds. This does not retroactively establish the production of earlier wheels or claim complete independent reproducibility. See [source materials](docs/source-materials.md).
