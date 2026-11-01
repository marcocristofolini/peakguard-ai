#!/usr/bin/env bash
set -euo pipefail
# Nome fixo: nunca usa contexto kubectl corrente ou cluster externo.
"${KIND:-/tmp/kind}" delete cluster --name peakguard-p6
