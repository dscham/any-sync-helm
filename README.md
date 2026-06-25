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
  --set externalHostname=anytype.example.com
```

Point the DNS record for `anytype.example.com` at any of your cluster node IPs.

### What Happens on Install

The chart replicates the full setup flow of the upstream docker-compose project:

1. **Init Job** (pre-install) — generates crypto keys, node configuration files, and `client.yml` using the official `any-sync-tools` image. Scripts and config templates are mounted from ConfigMaps — no custom image build needed.
2. **MongoDB replica set** — starts with `--replSet` and a liveness probe that automatically runs `rs.initiate()` on first boot.
3. **MinIO bucket creation** (post-install) — creates the S3 bucket for file storage.
4. **Coordinator bootstrap** (post-install) — registers the network configuration with the coordinator.
5. **Client config export** (post-install) — parses the generated `client.yml` and stores it as a ConfigMap for easy retrieval.
6. **All sync services start** — coordinator, consensus node, file node, and 3 sync nodes.

### Retrieving the Client Config

After install, retrieve the `client.yml` to configure your Anytype apps:

```bash
# From the ConfigMap (persisted)
kubectl get configmap <release>-any-sync-client-config -o jsonpath='{.data.client\.yml}'

# Or from the export job logs
kubectl logs job/<release>-any-sync-export-client-config
```

Import this file in your Anytype app under **Settings → Data Management → Self-Hosted**.

## Required Values

| Value | Description |
|---|---|
| `externalHostname` | The FQDN or IP that Anytype clients use to connect. Gets embedded into `client.yml` with the correct NodePort numbers. |

## Networking

All any-sync services are exposed via **NodePort** — no ingress controller or load balancer required. This works on any Kubernetes cluster out of the box.

### Exposed Ports

| Service | TCP NodePort | QUIC/UDP NodePort | Internal Port |
|---|---|---|---|
| Sync Node 1 | 30001 | 30011 | 1001 / 1011 |
| Sync Node 2 | 30002 | 30012 | 1002 / 1012 |
| Sync Node 3 | 30003 | 30013 | 1003 / 1013 |
| Coordinator | 30004 | 30014 | 1004 / 1014 |
| Filenode | 30005 | 30015 | 1005 / 1015 |
| Consensus Node | 30006 | 30016 | 1006 / 1016 |

NodePort numbers are configurable via `values.yaml` (see below).

The init job automatically patches `client.yml` so that external addresses use the NodePort numbers while internal service-to-service communication uses the original ports.

## Values Reference

### Global

| Value | Default | Description |
|---|---|---|
| `externalHostname` | `""` (**required**) | External FQDN or IP for client connections |
| `maxMsgSizeMb` | `256` | GRPC/Yamux max message size. Increase this if you need to upload very large files. |

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
| `coordinator.port` | `1004` | Internal TCP port |
| `coordinator.quicPort` | `1014` | Internal QUIC port |
| `coordinator.nodePort` | `30004` | External TCP NodePort |
| `coordinator.quicNodePort` | `30014` | External QUIC NodePort |
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
| `filenode.port` | `1005` | Internal TCP port |
| `filenode.quicPort` | `1015` | Internal QUIC port |
| `filenode.nodePort` | `30005` | External TCP NodePort |
| `filenode.quicNodePort` | `30015` | External QUIC NodePort |
| `filenode.defaultLimit` | `1099511627776` | Per-account storage quota in bytes (1 TiB) |
| `filenode.resources.limits.memory` | `500M` | Container memory limit |
| `filenode.persistence.size` | `1Gi` | PVC size |
| `filenode.persistence.storageClass` | `""` (default) | StorageClass name |

### Sync Nodes (1–3)

Replace `N` with `1`, `2`, or `3` (keys: `syncNode1`, `syncNode2`, `syncNode3`).

| Value | Default (node 1/2/3) | Description |
|---|---|---|
| `syncNodeN.image.repository` | `ghcr.io/anyproto/any-sync-node` | Image |
| `syncNodeN.image.tag` | `v0.11.1` | Version |
| `syncNodeN.port` | `1001` / `1002` / `1003` | Internal TCP port |
| `syncNodeN.quicPort` | `1011` / `1012` / `1013` | Internal QUIC port |
| `syncNodeN.nodePort` | `30001` / `30002` / `30003` | External TCP NodePort |
| `syncNodeN.quicNodePort` | `30011` / `30012` / `30013` | External QUIC NodePort |
| `syncNodeN.resources.limits.memory` | `500M` | Container memory limit |
| `syncNodeN.persistence.size` | `10Gi` | PVC size |
| `syncNodeN.persistence.storageClass` | `""` (default) | StorageClass name |

### Consensus Node

| Value | Default | Description |
|---|---|---|
| `consensusnode.image.repository` | `ghcr.io/anyproto/any-sync-consensusnode` | Image |
| `consensusnode.image.tag` | `v0.7.2` | Version |
| `consensusnode.port` | `1006` | Internal TCP port |
| `consensusnode.quicPort` | `1016` | Internal QUIC port |
| `consensusnode.nodePort` | `30006` | External TCP NodePort |
| `consensusnode.quicNodePort` | `30016` | External QUIC NodePort |
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
│          Core Services (NodePort: 30001–30016)               │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐               │
│  │sync-node-1 │ │sync-node-2 │ │sync-node-3 │ Deployments   │
│  └────────────┘ └────────────┘ └────────────┘               │
│  ┌────────────┐ ┌────────────┐ ┌──────────────┐             │
│  │coordinator │ │  filenode   │ │consensusnode │ Deployments  │
│  └────────────┘ └────────────┘ └──────────────┘             │
├───────────────────────────────────────────────────────────────┤
│                Data Services (ClusterIP only)                │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐               │
│  │  MongoDB   │ │   Redis    │ │   MinIO    │ StatefulSets   │
│  └────────────┘ └────────────┘ └────────────┘               │
└───────────────────────────────────────────────────────────────┘
```

## How It Works

This chart is **auto-generated** from the upstream [any-sync-dockercompose](https://github.com/anyproto/any-sync-dockercompose) repository:

1. **`source` branch** contains the upstream docker-compose files, plus:
   - `scripts/postprocess.py` — transforms kompose output into proper Helm templates
   - `helm-templates/` — hand-crafted templates for init, client config export, and secrets
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
