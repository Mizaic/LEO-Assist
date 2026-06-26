#!/usr/bin/env bash
set -euo pipefail

RG="${1:-leo-ai-dev}"
NS="${2:-mizaicai-dev-bus}"

APPS=(
  core-api
  ui
  terminology-api
  fhir-api
  analytics-api
  model-inference
  training-worker
  pipeline-worker
)

echo "== Container Apps summary (${RG}) =="
az containerapp list \
  --resource-group "${RG}" \
  --query "[].{name:name,provisioning:properties.provisioningState,running:properties.runningStatus,latestRevision:properties.latestRevisionName}" \
  --output table
echo

echo "== Revision health (active revisions only) =="
for app in "${APPS[@]}"; do
  echo "-- ${app} --"
  az containerapp revision list \
    --resource-group "${RG}" \
    --name "${app}" \
    --query "[?properties.active==\`true\`].{name:name,health:properties.healthState,state:properties.runningState,replicas:properties.replicas}" \
    --output table
done
echo

echo "== Service Bus queue health (${NS}/pipeline-jobs) =="
az servicebus queue show \
  --resource-group "${RG}" \
  --namespace-name "${NS}" \
  --name pipeline-jobs \
  --query "{status:status,active:countDetails.activeMessageCount,deadLetter:countDetails.deadLetterMessageCount,scheduled:countDetails.scheduledMessageCount,transferDeadLetter:countDetails.transferDeadLetterMessageCount}" \
  --output table
echo

echo "== Pipeline worker system warnings (tail 120) =="
az containerapp logs show \
  --resource-group "${RG}" \
  --name pipeline-worker \
  --type system \
  --tail 120
