"""Assert and patch the pinned OpenShell 0.1.4 chart's certgen hooks."""

import sys
from pathlib import Path

chart = Path(sys.argv[1])
assert "version: 0.1.4" in (chart / "Chart.yaml").read_text()
path = chart / "templates/certgen.yaml"
source = path.read_text()
needle = "      restartPolicy: OnFailure\n"
patch = """      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        seccompProfile:
          type: RuntimeDefault
"""
if source.count(patch + needle) == 2:
    print("Pinned chart already patched")
else:
    assert source.count(needle) == 2, "Unexpected certgen chart; inspect before patching"
    assert "      securityContext:" not in source, "Unexpected pod security settings"
    path.write_text(source.replace(needle, patch + needle))
    print("Patched both certgen hook pod security contexts")
