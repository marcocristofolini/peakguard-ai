#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
export KUBECONFIG="$PWD/local/p6/.kubeconfig"
HELM="${HELM:-helm}"
if ! command -v "$HELM" >/dev/null 2>&1; then
  if [[ -x /tmp/linux-amd64/helm ]]; then HELM=/tmp/linux-amd64/helm
  else echo "Instale Helm 3 primeiro." >&2; exit 1
  fi
fi
kubectl config current-context | grep -qx kind-peakguard-p6
kubectl get namespace peakguard-p6 >/dev/null
"$HELM" repo add kedacore https://kedacore.github.io/charts --force-update
"$HELM" repo add opencost-charts https://opencost.github.io/opencost-helm-chart --force-update
"$HELM" repo update
"$HELM" upgrade --install keda kedacore/keda --version 2.21.0 -n keda --create-namespace --wait --timeout 300s
"$HELM" upgrade --install opencost opencost-charts/opencost --version 2.5.33 -n opencost --create-namespace -f local/p6/opencost-values.yaml --wait --timeout 300s
kubectl -n peakguard-p6 apply -f local/p6/keda-demo.yaml
kubectl -n peakguard-p6 rollout status deployment/documents-keda --timeout=180s
kubectl -n peakguard-p6 get scaledobject documents-keda
kubectl -n keda get pods
kubectl -n opencost get pods
