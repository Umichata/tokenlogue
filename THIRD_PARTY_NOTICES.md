# Third-Party Notices

This preliminary registry covers the direct production dependencies declared
by Tokenlogue. Versions and licenses were checked against the installed Python
package metadata and, where supplied by the package, its included license
file.

## Flet

- Version: `0.86.5`
- License: Apache License 2.0 (`Apache-2.0`)
- Upstream: <https://github.com/flet-dev/flet>
- Purpose: cross-platform application framework and user-interface runtime.
- Verification: the installed package metadata declares the SPDX license
  expression `Apache-2.0`.

## Flet Secure Storage

- Version: `0.86.5`
- License: Apache License 2.0 (`Apache-2.0`)
- Upstream:
  <https://github.com/flet-dev/flet/tree/main/sdk/python/packages/flet-secure-storage>
- Purpose: platform-backed protected storage for the OpenRouter API key and
  registration identifier.
- Verification: the installed distribution includes the canonical Apache
  License 2.0 text in its packaged `LICENSE` file.

## HTTPX

- Version: `0.28.1`
- License: BSD 3-Clause License (`BSD-3-Clause`)
- Upstream: <https://github.com/encode/httpx>
- Purpose: asynchronous HTTPS requests to the OpenRouter API.
- Verification: the installed package metadata declares `BSD-3-Clause`, and
  the distribution includes the corresponding license text in `LICENSE.md`.

## Scope of this registry

This file is not yet the complete notice set for a binary release. After real
platform bundles are produced, the licenses and required notices for Flutter,
Dart, the embedded Python runtime, Flutter plugins, transitive Python
dependencies, native libraries, and all other bundled components must be
generated, reviewed, and included as required by their respective licenses.
