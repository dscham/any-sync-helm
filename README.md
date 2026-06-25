# any-sync Helm Chart

Helm chart for deploying the [Anytype any-sync](https://github.com/anyproto/any-sync-dockercompose) self-hosted infrastructure on Kubernetes.

**This branch (`main`) is auto-generated.** The source code, generation scripts, and hand-crafted templates live on the [`source`](../../tree/source) branch.

## Quick Start

```bash
# Clone the chart
git clone https://github.com/dscham/any-sync-helm.git
cd any-sync-helm

# Install (you MUST set externalHostname)
helm install any-sync ./ \
  --set externalHostname=anytype.example.com \
  --set ingress.type=traefik
```

After install, retrieve the client config for your Anytype apps:

```bash
# From the ConfigMap (persisted)
kubectl get configmap <release>-any-sync-client-config -o jsonpath='{.data.client\.yml}'

# Or from the export-client-config job logs
kubectl logs job/<release>-any-sync-export-client-config
```

## Required Values

These **must** be set — the chart will not produce a working deployment without them.

| Value | Description |
|---|---|
| `externalHostname` | The external hostname or IP that Anytype clients use to reach the sync services. This gets embedded into `client.yml`. For example, a public domain pointed at your ingress. |

## Values Reference

### Global

| Value | Default | Description |
|---|---|---|
| `externalHostname` | `""` (**required**) | External hostname/IP for client connections |
| `ingress.type` | `none` | Ingress controller: `none`, `traefik`, `nginx`, or `haproxy` |
| `ingress.nginx.configMapNamespace` | `""` | Namespace of the NGINX ingress controller (if different from release) |

### MongoDB

| Value | Default | Description |
|---|---|---|
| `mongo.image.repository` | `mongo` | MongoDB image |
| `mongo.image.tag` | `7.0.28` | MongoDB version |
| `mongo.port` | `27001` | MongoDB port |
| `mongo.replicaSet` | `rs0` | Replica set name |
| `mongo.persistence.size` | `10Gi` | PVC size |
| `mongo.persistence.storageClass` | `""` (default) | StorageClass name |

### Redis

| Value | Default | Description |
|---|---|---|
| `redis.image.repository` | `redis/redis-stack-server` | Redis image |
| `redis.image.tag` | `7.2.0-v6` | Redis version |
| `redis.port` | `6379` | Redis port |
| `redis.maxMemory` | `256mb` | Max memory limit |
| `redis.persistence.size` | `5Gi` | PVC size |
| `redis.persistence.storageClass` | `""` (default) | StorageClass name |

### MinIO (S3-compatible object storage)

| Value | Default | Description |
|---|---|---|
| `minio.image.repository` | `minio/minio` | MinIO image |
| `minio.image.tag` | `RELEASE.2024-07-04T14-25-45Z` | MinIO version |
| `minio.port` | `9000` | S3 API port |
| `minio.webPort` | `9001` | MinIO web console port |
| `minio.bucket` | `minio-bucket` | Default bucket name |
| `minio.accessKey` | `minio_access_key` | S3 access key (change in production!) |
| `minio.secretKey` | `minio_secret_key` | S3 secret key (change in production!) |
| `minio.persistence.size` | `50Gi` | PVC size |
| `minio.persistence.storageClass` | `""` (default) | StorageClass name |

### Coordinator

| Value | Default | Description |
|---|---|---|
| `coordinator.image.repository` | `ghcr.io/anyproto/any-sync-coordinator` | Image |
| `coordinator.image.tag` | `v0.9.1` | Version |
| `coordinator.port` | `1004` | TCP (yamux) port |
| `coordinator.quicPort` | `1014` | QUIC transport port |
| `coordinator.limits.spaceMembersRead` | `1000` | Max space members (read) |
| `coordinator.limits.spaceMembersWrite` | `1000` | Max space members (write) |
| `coordinator.limits.sharedSpacesLimit` | `1000` | Max shared spaces per account |
| `coordinator.resources.limits.memory` | `500M` | Container memory limit |
| `coordinator.persistence.size` | `1Gi` | PVC size |
| `coordinator.persistence.storageClass` | `""` (default) | StorageClass name |

### Filenode

| Value | Default | Description |
|---|---|---|
| `filenode.image.repository` | `ghcr.io/anyproto/any-sync-filenode` | Image |
| `filenode.image.tag` | `v0.11.1` | Version |
| `filenode.port` | `1005` | TCP (yamux) port |
| `filenode.quicPort` | `1015` | QUIC transport port |
| `filenode.defaultLimit` | `1099511627776` | Per-account storage quota in bytes (default: 1 TiB) |
| `filenode.resources.limits.memory` | `500M` | Container memory limit |
| `filenode.persistence.size` | `1Gi` | PVC size |
| `filenode.persistence.storageClass` | `""` (default) | StorageClass name |

### Sync Nodes (1–3)

Each sync node has identical configuration keys. Replace `N` with `1`, `2`, or `3` (keys: `syncNode1`, `syncNode2`, `syncNode3`).

| Value | Default (node 1/2/3) | Description |
|---|---|---|
| `syncNodeN.image.repository` | `ghcr.io/anyproto/any-sync-node` | Image |
| `syncNodeN.image.tag` | `v0.11.1` | Version |
| `syncNodeN.port` | `1001` / `1002` / `1003` | TCP (yamux) port |
| `syncNodeN.quicPort` | `1011` / `1012` / `1013` | QUIC transport port |
| `syncNodeN.resources.limits.memory` | `500M` | Container memory limit |
| `syncNodeN.persistence.size` | `10Gi` | PVC size |
| `syncNodeN.persistence.storageClass` | `""` (default) | StorageClass name |

### Consensus Node

| Value | Default | Description |
|---|---|---|
| `consensusnode.image.repository` | `ghcr.io/anyproto/any-sync-consensusnode` | Image |
| `consensusnode.image.tag` | `v0.7.2` | Version |
| `consensusnode.port` | `1006` | TCP (yamux) port |
| `consensusnode.quicPort` | `1016` | QUIC transport port |
| `consensusnode.resources.limits.memory` | `500M` | Container memory limit |
| `consensusnode.persistence.size` | `1Gi` | PVC size |
| `consensusnode.persistence.storageClass` | `""` (default) | StorageClass name |

### Utility Services

| Value | Default | Description |
|---|---|---|
| `netcheck.image.repository` | `ghcr.io/anyproto/any-sync-tools` | Network checker image |
| `netcheck.image.tag` | `latest` | Version |
| `netcheck.enabled` | `true` | Deploy the netcheck container |
| `init.image.repository` | `ghcr.io/anyproto/any-sync-tools` | Init job base image |
| `init.image.tag` | `latest` | Version |
| `coordinatorBootstrap.image.repository` | `ghcr.io/anyproto/any-sync-coordinator` | Bootstrap job image |
| `coordinatorBootstrap.image.tag` | `v0.9.1` | Version |
| `createBucket.image.repository` | `minio/mc` | MinIO client image |
| `createBucket.image.tag` | `latest` | Version |
| `exportClientConfig.image.repository` | `bitnami/kubectl` | Client config export job image |
| `exportClientConfig.image.tag` | `latest` | Version |

## Ingress

The chart supports four ingress modes:

| `ingress.type` | Controller | What gets created |
|---|---|---|
| `none` (default) | — | No ingress resources; services use ClusterIP |
| `traefik` | Traefik v3 | `IngressRouteTCP` + `IngressRouteUDP` CRDs |
| `nginx` | NGINX Ingress Controller | `tcp-services` + `udp-services` ConfigMaps |
| `haproxy` | HAProxy Ingress Controller | TCP service proxy ConfigMap |

### Exposed Ports

All any-sync services communicate over TCP (yamux) and UDP (QUIC). The following ports need to be reachable by Anytype clients:

| Service | TCP Port | QUIC Port |
|---|---|---|
| Sync Node 1 | 1001 | 1011 |
| Sync Node 2 | 1002 | 1012 |
| Sync Node 3 | 1003 | 1013 |
| Coordinator | 1004 | 1014 |
| Filenode | 1005 | 1015 |
| Consensus Node | 1006 | 1016 |

### Traefik

Requires the Traefik IngressRoute CRDs. The chart creates `IngressRouteTCP` and `IngressRouteUDP` resources directly.

Your Traefik Helm values must expose the ports as entrypoints. See `traefik-values-snippet.yaml` included in the chart for a working example.

### NGINX

NGINX Ingress Controller exposes TCP/UDP services via ConfigMaps. The chart creates `tcp-services` and `udp-services` ConfigMaps.

You must configure your NGINX controller deployment to use these ConfigMaps. See `nginx-values-snippet.yaml` included in the chart for the required configuration.

If your NGINX controller runs in a different namespace than the chart, set:

```yaml
ingress:
  nginx:
    configMapNamespace: ingress-nginx  # your controller's namespace
```

### HAProxy

Similar to NGINX, uses a ConfigMap-based approach. The chart creates the TCP proxy ConfigMap that HAProxy Ingress reads.

## Architecture

```
┌───────────────────────────────────────────────────────────────┐
│                    Helm pre-install hooks                     │
│  ┌──────────────┐                                            │
│  │  any-sync-init│ generates crypto keys + node configs      │
│  │  (Job)        │ → writes to shared PVCs                   │
│  └──────────────┘                                            │
├───────────────────────────────────────────────────────────────┤
│                    Helm post-install hooks                    │
│  ┌────────────────────┐  ┌──────────────┐  ┌───────────────┐ │
│  │coordinator-bootstrap│  │ create-bucket │  │export-client  │ │
│  │(Job)                │  │ (Job)         │  │-config (Job)  │ │
│  └────────────────────┘  └──────────────┘  └───────────────┘ │
├───────────────────────────────────────────────────────────────┤
│                      Core Services                           │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐               │
│  │sync-node-1 │ │sync-node-2 │ │sync-node-3 │ Deployments   │
│  └────────────┘ └────────────┘ └────────────┘               │
│  ┌────────────┐ ┌────────────┐ ┌──────────────┐             │
│  │coordinator │ │  filenode   │ │consensusnode │ Deployments  │
│  └────────────┘ └────────────┘ └──────────────┘             │
├───────────────────────────────────────────────────────────────┤
│                    Data Services                             │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐               │
│  │  MongoDB   │ │   Redis    │ │   MinIO    │ StatefulSets   │
│  └────────────┘ └────────────┘ └────────────┘               │
└───────────────────────────────────────────────────────────────┘
```

## How It Works

This chart is **auto-generated** from the upstream [any-sync-dockercompose](https://github.com/anyproto/any-sync-dockercompose) repository:

1. **`source` branch** contains the upstream docker-compose files, plus:
   - `scripts/postprocess.py` — transforms kompose output into proper Helm templates
   - `helm-templates/` — hand-crafted templates for ingress, init, and client config export
   - `generate-chart.sh` — local generation script
   - `.github/workflows/` — CI automation

2. **GitHub Actions** automatically:
   - Syncs upstream changes daily (`sync-upstream.yml`)
   - Regenerates the chart on every push to `source` (`generate-chart.yml`)
   - Publishes the chart to the `main` branch

3. **`main` branch** contains only the generated chart — ready to `helm install`.

## Development

```bash
# Switch to source branch
git checkout source

# Install kompose (https://kompose.io)
# Install Python 3 with PyYAML

# Generate the chart locally
./generate-chart.sh

# Or manually:
cp .env.example .env
kompose convert -c -f docker-compose.yml -o .tmp-chart
python3 scripts/postprocess.py
cp helm-templates/* charts/any-sync/templates/

# Lint
helm lint charts/any-sync

# Test rendering
helm template test charts/any-sync --set externalHostname=test.example.com
```

## License

This project is a fork of [anyproto/any-sync-dockercompose](https://github.com/anyproto/any-sync-dockercompose). See [LICENSE.md](LICENSE.md) for details.
