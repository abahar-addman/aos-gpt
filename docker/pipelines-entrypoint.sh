#!/bin/bash
set -e

PIPELINE_DIR="/app/pipelines"

# ── Azure Blob Storage sync ─────────────────────────────────────────────────
# On container start, download any pipeline .py files from the Azure
# "aos-pipeline" blob container so they survive container recreation.
#
# Required env vars (set in docker-compose or .env):
#   AZURE_STORAGE_ENDPOINT          - e.g. https://aos1.blob.core.usgovcloudapi.net
#   AZURE_PIPELINE_CONTAINER_NAME   - e.g. aos-pipeline  (defaults below)
#   AZURE_STORAGE_KEY               - storage account key
# ─────────────────────────────────────────────────────────────────────────────

CONTAINER_NAME="${AZURE_PIPELINE_CONTAINER_NAME:-aos-pipeline}"

if [ -n "$AZURE_STORAGE_ENDPOINT" ] && [ -n "$AZURE_STORAGE_KEY" ]; then
    echo "[pipelines-entrypoint] Syncing pipelines from Azure Blob Storage..."
    echo "[pipelines-entrypoint]   endpoint:  $AZURE_STORAGE_ENDPOINT"
    echo "[pipelines-entrypoint]   container: $CONTAINER_NAME"

    python3 -c "
import os, sys
from azure.storage.blob import BlobServiceClient

endpoint   = os.environ['AZURE_STORAGE_ENDPOINT']
key        = os.environ['AZURE_STORAGE_KEY']
container  = '${CONTAINER_NAME}'
target_dir = '${PIPELINE_DIR}'

try:
    client = BlobServiceClient(account_url=endpoint, credential=key)
    container_client = client.get_container_client(container)
    blobs = list(container_client.list_blobs())
    py_blobs = [b for b in blobs if b.name.endswith('.py')]

    if not py_blobs:
        print('[pipelines-entrypoint] No .py files found in Azure container.')
        sys.exit(0)

    os.makedirs(target_dir, exist_ok=True)
    for blob in py_blobs:
        dest = os.path.join(target_dir, blob.name)
        print(f'[pipelines-entrypoint]   downloading {blob.name} -> {dest}')
        blob_client = container_client.get_blob_client(blob.name)
        with open(dest, 'wb') as f:
            f.write(blob_client.download_blob().readall())

    print(f'[pipelines-entrypoint] Synced {len(py_blobs)} pipeline(s) from Azure.')
except Exception as e:
    print(f'[pipelines-entrypoint] WARNING: Azure sync failed: {e}', file=sys.stderr)
    print('[pipelines-entrypoint] Continuing with existing local pipelines...')
"
else
    echo "[pipelines-entrypoint] Azure storage not configured, skipping sync."
fi

echo "[pipelines-entrypoint] Starting pipelines server..."

# Enable ddtrace log injection so dd.trace_id/dd.span_id are stamped onto
# every LogRecord — our JSON formatter inside v3_agent_pipe.py lifts them
# into Datadog's reserved keys so the Logs UI auto-links to APM traces.
export DD_LOGS_INJECTION=${DD_LOGS_INJECTION:-true}

# Hand off to the original pipelines entrypoint / CMD under ddtrace-run.
# DD_SERVICE / DD_ENV / DD_VERSION are read from env (set in docker-compose).
exec ddtrace-run bash start.sh
