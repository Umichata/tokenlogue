#!/bin/sh
set -eu
umask 022
export LC_ALL=C TZ=UTC
mkdir -p /opt/runtime-evidence
cp /lib/apk/db/installed /opt/runtime-evidence/base-installed
cd /locked
sha256sum -c SHA256SUMS
# No repository index participates in resolution. Every package is a local APK.
if apk --no-network --repositories-file /dev/null verify apks/*.apk \
    > /opt/runtime-evidence/apk-signatures.txt 2>&1; then
    cat /opt/runtime-evidence/apk-signatures.txt
else
    status=$?
    cat /opt/runtime-evidence/apk-signatures.txt >&2 || true
    exit "$status"
fi
apk --no-network --repositories-file /dev/null add --no-cache apks/*.apk
cp /lib/apk/db/installed /opt/runtime-evidence/installed
python3 - <<'PY'
import json
from pathlib import Path
from runtime_inputs import check_inventory, parse_inventory, write_json

for label, filename in [('base', 'base-installed'), ('installed', 'installed')]:
    actual = parse_inventory(Path('/opt/runtime-evidence', filename).read_text())
    check_inventory(actual, json.loads(Path('/locked', label + '.json').read_text()))
write_json(Path('/opt/runtime-evidence/inventory.json'), {
    'result': 'PASS', 'apk_signatures': 'PASS', 'installed': actual,
})
PY
