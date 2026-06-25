# any-sync Helm Chart

Helm chart for deploying the [Anytype any-sync](https://github.com/anyproto/any-sync-dockercompose) self-hosted infrastructure on Kubernetes.

**This branch is auto-generated.** The chart is built from the [`source`](../../tree/source) branch by GitHub Actions.

## Quick Start

```bash
# Add as a local chart
helm install any-sync ./

# With Traefik ingress
helm install any-sync ./ --set ingress.type=traefik

# With NGINX ingress
helm install any-sync ./ --set ingress.type=nginx
```

## Ingress Support

| `ingress.type` | Controller | What gets created |
|---|---|---|
| `none` (default) | — | No ingress resources |
| `traefik` | Traefik v3 | IngressRouteTCP + IngressRouteUDP CRDs |
| `nginx` | NGINX Ingress | tcp-services + udp-services ConfigMaps |
| `haproxy` | HAProxy Ingress | TCP service proxy ConfigMap |

See `traefik-values-snippet.yaml` or `nginx-values-snippet.yaml` for the required ingress controller configuration.

## Client Configuration

After install, retrieve the client config for your Anytype apps:

```bash
kubectl get configmap <release>-any-sync-client-config -o jsonpath='{.data.client\.yml}'
```

## Source

The generation scripts and hand-crafted templates live on the [`source`](../../tree/source) branch.
