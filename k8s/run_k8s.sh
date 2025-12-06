#!/usr/bin/env bash
set -euo pipefail

NS="hzz-rabbit"

echo "[run_k8s] Applying core manifests"
kubectl apply -f k8s-all.yaml

echo "[run_k8s] Deleting old jobs"
kubectl delete job producer-job combiner-job -n "$NS" --ignore-not-found=true

echo "[run_k8s] Re-applying jobs"
kubectl apply -f k8s-all.yaml

echo "[run_k8s] Waiting for producer job to complete"
kubectl wait --for=condition=complete job/producer-job -n "$NS" --timeout=900s

echo "[run_k8s] Waiting for combiner job to complete"
kubectl wait --for=condition=complete job/combiner-job -n "$NS" --timeout=900s

echo "[run_k8s] Creating outputs pod"
kubectl apply -f outputs.yaml

echo "[run_k8s] Waiting for outputs to be ready"
kubectl wait --for=condition=Ready pod/outputs-helper -n "$NS" --timeout=120s

mkdir -p outputs

echo "[run_k8s] Copying outputs locally"
kubectl cp -n "$NS" outputs-helper:/outputs ./outputs

echo "[run_k8s] Cleaning up outputs"
kubectl delete pod outputs-helper -n "$NS" --wait=true

echo "[run_k8s] Done."
