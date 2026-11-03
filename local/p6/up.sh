#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
KIND=${KIND:-/tmp/kind}
export KUBECONFIG="$PWD/local/p6/.kubeconfig"
if ! "$KIND" get clusters | rg -qx peakguard-p6; then
  "$KIND" create cluster --name peakguard-p6 --image kindest/node@sha256:099e049362a1526b2db71494e1947aae99bd16290d7c895f2b7ea312e3cbfaed --config local/p6/kind.yaml --kubeconfig "$KUBECONFIG" --wait 120s
fi
"$KIND" export kubeconfig --name peakguard-p6 --kubeconfig "$KUBECONFIG"
docker update --cpus 4 --memory 6g --memory-swap 6g peakguard-p6-control-plane
kubectl --context kind-peakguard-p6 wait --for=condition=Ready node --all --timeout=120s
docker build -t peakguard-p6:local local/p6
"$KIND" load docker-image peakguard-p6:local --name peakguard-p6
# Somente o cluster Kind dedicado usa certificados kubelet autoassinados.
if ! kubectl --context kind-peakguard-p6 -n kube-system get deployment metrics-server >/dev/null 2>&1; then
  kubectl --context kind-peakguard-p6 apply -f https://github.com/kubernetes-sigs/metrics-server/releases/download/v0.8.0/components.yaml
fi
kubectl --context kind-peakguard-p6 -n kube-system patch deployment metrics-server --type=json -p='[{"op":"replace","path":"/spec/template/spec/containers/0/args","value":["--cert-dir=/tmp","--secure-port=10250","--kubelet-preferred-address-types=InternalIP,ExternalIP,Hostname","--kubelet-use-node-status-port","--metric-resolution=15s","--kubelet-insecure-tls"]},{"op":"add","path":"/spec/template/spec/containers/0/resources/limits","value":{"cpu":"500m","memory":"256Mi"}}]'
kubectl --context kind-peakguard-p6 -n kube-system rollout status deployment/metrics-server --timeout=180s
kubectl --context kind-peakguard-p6 apply -f local/p6/resources.yaml
kubectl --context kind-peakguard-p6 -n peakguard-p6 rollout status deployment/documents --timeout=180s
kubectl --context kind-peakguard-p6 -n peakguard-p6 rollout status deployment/prometheus --timeout=180s
