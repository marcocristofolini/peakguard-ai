#!/usr/bin/env bash
# P17: só KEDA 2.21 (sem OpenCost e sem a demo documents-keda) no cluster Kind dedicado.
set -euo pipefail
cd "$(dirname "$0")/../.."
export KUBECONFIG="$PWD/local/p6/.kubeconfig"
HELM="${HELM:-helm}"
kubectl config current-context | grep -qx kind-peakguard-p6
kubectl get namespace peakguard-p6 >/dev/null
"$HELM" repo add kedacore https://kedacore.github.io/charts --force-update
"$HELM" repo update kedacore
"$HELM" upgrade --install keda kedacore/keda --version 2.21.0 -n keda --create-namespace --wait --timeout 300s
kubectl -n keda get pods
