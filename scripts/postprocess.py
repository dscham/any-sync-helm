#!/usr/bin/env python3
"""
postprocess.py — Transform kompose scaffolding into a proper Helm chart.

Reads raw kompose YAML output from .tmp-chart/templates/,
applies transformations, and writes the final chart to charts/any-sync/.

Transformations:
  1. Deployment → StatefulSet for mongo, redis, minio
  2. Pod → Job for init, bootstrap, create-bucket (with Helm hook annotations)
  3. Hardcoded values → {{ .Values.* }} Helm template references
  4. PVCs → volumeClaimTemplates for StatefulSets
  5. Annotation/label cleanup
  6. Generate values.yaml from .env.example defaults
"""

import os
import sys
import re
import copy
import glob
import yaml


# ---------------------------------------------------------------------------
# Configuration: which services get which treatment
# ---------------------------------------------------------------------------

STATEFULSET_SERVICES = {"mongo-1", "redis", "minio"}

JOB_SERVICES = {
    "any-sync-init": {
        "hook": "pre-install,pre-upgrade",
        "hook_weight": "-5",
        "hook_delete_policy": "before-hook-creation",
    },
    "any-sync-coordinator-bootstrap": {
        "hook": "post-install,post-upgrade",
        "hook_weight": "1",
        "hook_delete_policy": "before-hook-creation",
    },
    "create-bucket": {
        "hook": "post-install,post-upgrade",
        "hook_weight": "2",
        "hook_delete_policy": "before-hook-creation",
    },
}

# Services that should NOT have a Service resource generated
NO_SERVICE = {"netcheck", "any-sync-init", "any-sync-coordinator-bootstrap", "create-bucket"}

# Maps kompose service names to values.yaml keys
SERVICE_VALUE_KEYS = {
    "mongo-1": "mongo",
    "redis": "redis",
    "minio": "minio",
    "any-sync-coordinator": "coordinator",
    "any-sync-filenode": "filenode",
    "any-sync-node-1": "syncNode1",
    "any-sync-node-2": "syncNode2",
    "any-sync-node-3": "syncNode3",
    "any-sync-consensusnode": "consensusnode",
    "netcheck": "netcheck",
    "any-sync-init": "init",
    "any-sync-coordinator-bootstrap": "coordinatorBootstrap",
    "create-bucket": "createBucket",
}

# Image defaults extracted from .env.example
IMAGE_DEFAULTS = {
    "mongo": {"repository": "mongo", "tag": "7.0.28"},
    "redis": {"repository": "redis/redis-stack-server", "tag": "7.2.0-v6"},
    "minio": {"repository": "minio/minio", "tag": "RELEASE.2024-07-04T14-25-45Z"},
    "coordinator": {"repository": "ghcr.io/anyproto/any-sync-coordinator", "tag": "latest"},
    "filenode": {"repository": "ghcr.io/anyproto/any-sync-filenode", "tag": "latest"},
    "syncNode1": {"repository": "ghcr.io/anyproto/any-sync-node", "tag": "latest"},
    "syncNode2": {"repository": "ghcr.io/anyproto/any-sync-node", "tag": "latest"},
    "syncNode3": {"repository": "ghcr.io/anyproto/any-sync-node", "tag": "latest"},
    "consensusnode": {"repository": "ghcr.io/anyproto/any-sync-consensusnode", "tag": "latest"},
    "netcheck": {"repository": "ghcr.io/anyproto/any-sync-tools", "tag": "latest"},
    "init": {"repository": "ghcr.io/anyproto/any-sync-tools", "tag": "latest"},
    "coordinatorBootstrap": {"repository": "ghcr.io/anyproto/any-sync-coordinator", "tag": "latest"},
    "createBucket": {"repository": "minio/mc", "tag": "latest"},
}


# ---------------------------------------------------------------------------
# YAML helpers
# ---------------------------------------------------------------------------

class LiteralStr(str):
    """String that should be rendered as a YAML literal (for Helm templates)."""
    pass


def literal_representer(dumper, data):
    """Don't quote strings that contain Helm template expressions."""
    if "{{" in data:
        # Use plain scalar style so {{ }} aren't quoted
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


yaml.add_representer(str, literal_representer)


def load_yaml(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def dump_yaml(data, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, width=200)


def load_all_yamls(directory):
    """Load all YAML files from a directory, returning list of (filename, data)."""
    results = []
    for filepath in sorted(glob.glob(os.path.join(directory, "*.yaml"))):
        data = load_yaml(filepath)
        if data:
            results.append((os.path.basename(filepath), data))
    return results


# ---------------------------------------------------------------------------
# Service name extraction
# ---------------------------------------------------------------------------

def get_service_name(data):
    """Extract the service name from kompose labels."""
    labels = data.get("metadata", {}).get("labels", {})
    return labels.get("io.kompose.service", "")


def get_value_key(service_name):
    """Map a service name to its values.yaml key."""
    return SERVICE_VALUE_KEYS.get(service_name, service_name.replace("-", "_"))


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

def clean_annotations(data):
    """Remove kompose-specific annotations from metadata and pod template."""
    for loc in [data, data.get("spec", {}).get("template", {})]:
        annotations = loc.get("metadata", {}).get("annotations", {})
        for key in list(annotations.keys()):
            if key.startswith("kompose."):
                del annotations[key]
        if not annotations and "annotations" in loc.get("metadata", {}):
            del loc["metadata"]["annotations"]


def clean_labels(data):
    """Replace io.kompose.service labels with app.kubernetes.io labels."""
    service_name = get_service_name(data)
    if not service_name:
        return

    for loc in [data, data.get("spec", {}).get("template", {})]:
        labels = loc.get("metadata", {}).get("labels", {})
        if "io.kompose.service" in labels:
            del labels["io.kompose.service"]
        labels["app.kubernetes.io/name"] = service_name
        labels["app.kubernetes.io/instance"] = '{{ .Release.Name }}'
        labels["app.kubernetes.io/managed-by"] = '{{ .Release.Service }}'

    # Also fix selector matchLabels
    spec = data.get("spec", {})
    match_labels = spec.get("selector", {}).get("matchLabels", {})
    if "io.kompose.service" in match_labels:
        del match_labels["io.kompose.service"]
        match_labels["app.kubernetes.io/name"] = service_name
        match_labels["app.kubernetes.io/instance"] = '{{ .Release.Name }}'


# ---------------------------------------------------------------------------
# Image templating
# ---------------------------------------------------------------------------

def templatize_image(data, value_key):
    """Replace hardcoded image with {{ .Values }} reference."""
    containers = (
        data.get("spec", {})
        .get("template", {})
        .get("spec", {})
        .get("containers", [])
    )
    if not containers:
        # For bare Pods (before Job wrapping), containers are at spec.containers
        containers = data.get("spec", {}).get("containers", [])

    for container in containers:
        if "image" in container:
            container["image"] = (
                f'{{{{ .Values.{value_key}.image.repository }}}}:'
                f'{{{{ .Values.{value_key}.image.tag }}}}'
            )


# ---------------------------------------------------------------------------
# Resource limit templating
# ---------------------------------------------------------------------------

def templatize_resources(data, value_key):
    """Replace hardcoded resource limits with {{ .Values }} references."""
    containers = (
        data.get("spec", {})
        .get("template", {})
        .get("spec", {})
        .get("containers", [])
    )
    for container in containers:
        resources = container.get("resources", {})
        limits = resources.get("limits", {})
        if "memory" in limits:
            # We inject both limits and requests for memory to prevent OOM
            limits["memory"] = f'{{{{ .Values.{value_key}.resources.limits.memory }}}}'
            if "requests" not in resources:
                resources["requests"] = {}
            resources["requests"]["memory"] = f'{{{{ .Values.{value_key}.resources.requests.memory }}}}'
            container["resources"] = resources


def templatize_secret_mounts(data, service_name):
    """Replace PVC mounts for config and AWS credentials with K8s Secret mounts."""
    config_mapping = {
        "any-sync-node-1": "node-1.yml",
        "any-sync-node-2": "node-2.yml",
        "any-sync-node-3": "node-3.yml",
        "any-sync-coordinator": "coordinator.yml",
        "any-sync-filenode": "filenode.yml",
        "any-sync-consensusnode": "consensusnode.yml"
    }
    if service_name not in config_mapping:
        return

    config_key = config_mapping[service_name]
    
    containers = data.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
    for container in containers:
        new_mounts = []
        for mount in container.get("volumeMounts", []):
            mount_path = mount.get("mountPath", "")
            if mount_path.startswith("/etc/any-sync-"):
                mount["name"] = "network-configs"
                mount["subPath"] = config_key
                mount["mountPath"] = mount_path + "/config.yml"
                new_mounts.append(mount)
                if service_name == "any-sync-coordinator":
                    new_mounts.append({
                        "name": "network-configs",
                        "mountPath": "/etc/any-sync-coordinator/network.yml",
                        "subPath": "network.yml"
                    })
            elif mount_path == "/root/.aws":
                mount["name"] = "network-configs"
                mount["subPath"] = "aws-credentials"
                mount["mountPath"] = "/root/.aws/credentials"
                new_mounts.append(mount)
            else:
                new_mounts.append(mount)
        container["volumeMounts"] = new_mounts

    volumes = data.get("spec", {}).get("template", {}).get("spec", {}).get("volumes", [])
    referenced_volumes = set()
    for container in containers:
        for mount in container.get("volumeMounts", []):
            referenced_volumes.add(mount["name"])
            
    new_volumes = []
    for vol in volumes:
        if vol.get("name") in referenced_volumes and vol.get("name") != "network-configs":
            new_volumes.append(vol)
            
    if "network-configs" in referenced_volumes:
        new_volumes.append({
            "name": "network-configs",
            "secret": {
                "secretName": '{{ include "any-sync.fullname" . }}-network-configs'
            }
        })
        
    data.setdefault("spec", {}).setdefault("template", {}).setdefault("spec", {})["volumes"] = new_volumes



# Port and service-name values that need templatizing
PORT_DEFAULTS = {
    "mongo": 27001,
    "redis": 6379,
    "minio": 9000,
    "coordinator": 1004,
    "filenode": 1005,
    "syncNode1": 1001,
    "syncNode2": 1002,
    "syncNode3": 1003,
    "consensusnode": 1006,
}

QUIC_PORT_DEFAULTS = {
    "coordinator": 1014,
    "filenode": 1015,
    "syncNode1": 1011,
    "syncNode2": 1012,
    "syncNode3": 1013,
    "consensusnode": 1016,
}

# Services exposed externally via NodePort
EXTERNAL_SERVICES = {
    "syncNode1", "syncNode2", "syncNode3",
    "coordinator", "filenode", "consensusnode",
}


def templatize_ports(data, value_key):
    """Replace hardcoded port numbers in container specs with {{ .Values }} references."""
    if value_key not in PORT_DEFAULTS:
        return

    default_port = PORT_DEFAULTS[value_key]
    port_ref = f'{{{{ .Values.{value_key}.port }}}}'

    # Templatize container ports and args
    containers = (
        data.get("spec", {})
        .get("template", {})
        .get("spec", {})
        .get("containers", [])
    )
    for container in containers:
        # Container ports
        for port_entry in container.get("ports", []):
            if port_entry.get("containerPort") == default_port:
                port_entry["containerPort"] = port_ref
            # QUIC port
            if value_key in QUIC_PORT_DEFAULTS:
                quic_default = QUIC_PORT_DEFAULTS[value_key]
                if port_entry.get("containerPort") == quic_default:
                    port_entry["containerPort"] = f'{{{{ .Values.{value_key}.quicPort }}}}'

        # Command args (e.g. mongo --port 27001)
        args = container.get("args", [])
        for i, arg in enumerate(args):
            if arg == str(default_port):
                args[i] = port_ref

        # Mongo-specific: templatize replica set name and port in liveness probe
        if value_key == "mongo":
            rs_ref = '{{ .Values.mongo.replicaSet }}'
            for arg_idx, arg in enumerate(args):
                if arg == "rs0":
                    args[arg_idx] = rs_ref

            probe = container.get("livenessProbe", {}).get("exec", {})
            cmd = probe.get("command", [])
            for i, c in enumerate(cmd):
                if isinstance(c, str) and "rs.initiate" in c:
                    c = c.replace("27001", '{{ .Values.mongo.port }}')
                    c = c.replace("rs0", '{{ .Values.mongo.replicaSet }}')
                    cmd[i] = c


def templatize_service_ports(data, value_key):
    """Replace hardcoded port numbers in Service specs with {{ .Values }} refs.

    For externally-exposed any-sync services, also:
    - Set type: NodePort
    - Add nodePort fields
    - Templatize QUIC ports
    """
    if value_key not in PORT_DEFAULTS:
        return

    default_port = PORT_DEFAULTS[value_key]
    port_ref = f'{{{{ .Values.{value_key}.port }}}}'

    is_external = value_key in EXTERNAL_SERVICES

    if is_external:
        data["spec"]["type"] = "NodePort"

    for port_entry in data.get("spec", {}).get("ports", []):
        # TCP port
        if port_entry.get("port") == default_port or port_entry.get("name") == str(default_port):
            port_entry["name"] = f'{value_key}-tcp'
            port_entry["port"] = port_ref
            port_entry["targetPort"] = port_ref
            if is_external:
                port_entry["nodePort"] = f'{{{{ .Values.{value_key}.nodePort }}}}'
        elif port_entry.get("targetPort") == default_port:
            port_entry["targetPort"] = port_ref
            if port_entry.get("port") == default_port:
                port_entry["port"] = port_ref

        # QUIC port
        if value_key in QUIC_PORT_DEFAULTS:
            quic_default = QUIC_PORT_DEFAULTS[value_key]
            if port_entry.get("port") == quic_default or port_entry.get("name") == str(quic_default):
                quic_ref = f'{{{{ .Values.{value_key}.quicPort }}}}'
                port_entry["name"] = f'{value_key}-quic'
                port_entry["port"] = quic_ref
                port_entry["targetPort"] = quic_ref
                if is_external:
                    port_entry["nodePort"] = f'{{{{ .Values.{value_key}.quicNodePort }}}}'



# ---------------------------------------------------------------------------
# Deployment → StatefulSet
# ---------------------------------------------------------------------------

def convert_to_statefulset(deployment, pvc_files, service_name, value_key):
    """Convert a Deployment to a StatefulSet with volumeClaimTemplates."""
    deployment["kind"] = "StatefulSet"
    deployment["apiVersion"] = "apps/v1"

    spec = deployment["spec"]

    # Add serviceName (required for StatefulSets)
    spec["serviceName"] = service_name

    # Remove strategy (invalid for StatefulSets)
    spec.pop("strategy", None)

    # Collect matching PVC definitions and convert to volumeClaimTemplates
    volume_claim_templates = []
    volumes = spec.get("template", {}).get("spec", {}).get("volumes", [])
    remaining_volumes = []

    for vol in volumes:
        pvc_ref = vol.get("persistentVolumeClaim", {}).get("claimName", "")
        if pvc_ref and pvc_ref in pvc_files:
            pvc_data = pvc_files[pvc_ref]
            vct = {
                "metadata": {"name": vol["name"]},
                "spec": {
                    "accessModes": pvc_data.get("spec", {}).get("accessModes", ["ReadWriteOnce"]),
                    "resources": {
                        "requests": {
                            "storage": f'{{{{ .Values.{value_key}.persistence.size }}}}'
                        }
                    },
                },
            }
            volume_claim_templates.append(vct)
        else:
            remaining_volumes.append(vol)

    if volume_claim_templates:
        spec["volumeClaimTemplates"] = volume_claim_templates

    spec["template"]["spec"]["volumes"] = remaining_volumes
    if not remaining_volumes:
        del spec["template"]["spec"]["volumes"]

    return deployment


# ---------------------------------------------------------------------------
# Pod → Job
# ---------------------------------------------------------------------------

def convert_to_job(pod, service_name):
    """Wrap a bare Pod spec in a Job with Helm hook annotations."""
    hook_config = JOB_SERVICES[service_name]

    job = {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {
            "name": pod["metadata"]["name"],
            "labels": pod["metadata"].get("labels", {}),
            "annotations": {
                "helm.sh/hook": hook_config["hook"],
                "helm.sh/hook-weight": hook_config["hook_weight"],
                "helm.sh/hook-delete-policy": hook_config["hook_delete_policy"],
            },
        },
        "spec": {
            "backoffLimit": 1,
            "template": {
                "metadata": {
                    "labels": pod["metadata"].get("labels", {}),
                },
                "spec": {
                    "containers": pod["spec"]["containers"],
                    "restartPolicy": "OnFailure",
                },
            },
        },
    }

    # Carry over volumes if present
    if "volumes" in pod["spec"]:
        job["spec"]["template"]["spec"]["volumes"] = pod["spec"]["volumes"]

    return job


# ---------------------------------------------------------------------------
# Service headless conversion for StatefulSets
# ---------------------------------------------------------------------------

def make_headless_service(service_data):
    """Set clusterIP: None for headless services (used by StatefulSets)."""
    service_data["spec"]["clusterIP"] = "None"
    return service_data


# ---------------------------------------------------------------------------
# Main processing
# ---------------------------------------------------------------------------

def generate_values(env_example_path):
    """Generate values.yaml from .env.example defaults."""
    values = {
        # REQUIRED: set this to the external hostname or IP where clients connect
        "externalHostname": "",
        "mongo": {
            "image": IMAGE_DEFAULTS["mongo"],
            "port": 27001,
            "replicaSet": "rs0",
            "persistence": {"size": "10Gi", "storageClass": ""},
        },
        "redis": {
            "image": IMAGE_DEFAULTS["redis"],
            "port": 6379,
            "maxMemory": "256mb",
            "persistence": {"size": "5Gi", "storageClass": ""},
        },
        "minio": {
            "image": IMAGE_DEFAULTS["minio"],
            "port": 9000,
            "webPort": 9001,
            "bucket": "minio-bucket",
            "accessKey": "minio_access_key",
            "secretKey": "minio_secret_key",
            "persistence": {"size": "120Gi", "storageClass": ""},
        },
        "coordinator": {
            "image": IMAGE_DEFAULTS["coordinator"],
            "port": 1004,
            "quicPort": 1014,
            "nodePort": 30004,
            "quicNodePort": 30014,
            "limits": {
                "spaceMembersRead": 1000,
                "spaceMembersWrite": 1000,
                "sharedSpacesLimit": 1000,
            },
            "resources": {
                "limits": {"memory": "1.5Gi"},
                "requests": {"memory": "1.5Gi"}
            },
            "persistence": {"size": "1Gi", "storageClass": ""},
        },
        "filenode": {
            "image": IMAGE_DEFAULTS["filenode"],
            "port": 1005,
            "quicPort": 1015,
            "nodePort": 30005,
            "quicNodePort": 30015,
            "defaultLimit": 107374182400,
            "resources": {
                "limits": {"memory": "1.5Gi"},
                "requests": {"memory": "1.5Gi"}
            },
            "persistence": {"size": "120Gi", "storageClass": ""},
        },
        "syncNode1": {
            "image": IMAGE_DEFAULTS["syncNode1"],
            "port": 1001,
            "quicPort": 1011,
            "nodePort": 30001,
            "quicNodePort": 30011,
            "resources": {
                "limits": {"memory": "1.5Gi"},
                "requests": {"memory": "1.5Gi"}
            },
            "persistence": {"size": "10Gi", "storageClass": ""},
        },
        "syncNode2": {
            "image": IMAGE_DEFAULTS["syncNode2"],
            "port": 1002,
            "quicPort": 1012,
            "nodePort": 30002,
            "quicNodePort": 30012,
            "resources": {
                "limits": {"memory": "1.5Gi"},
                "requests": {"memory": "1.5Gi"}
            },
            "persistence": {"size": "10Gi", "storageClass": ""},
        },
        "syncNode3": {
            "image": IMAGE_DEFAULTS["syncNode3"],
            "port": 1003,
            "quicPort": 1013,
            "nodePort": 30003,
            "quicNodePort": 30013,
            "resources": {
                "limits": {"memory": "1.5Gi"},
                "requests": {"memory": "1.5Gi"}
            },
            "persistence": {"size": "10Gi", "storageClass": ""},
        },
        "consensusnode": {
            "image": IMAGE_DEFAULTS["consensusnode"],
            "port": 1006,
            "quicPort": 1016,
            "nodePort": 30006,
            "quicNodePort": 30016,
            "resources": {
                "limits": {"memory": "1.5Gi"},
                "requests": {"memory": "1.5Gi"}
            },
            "persistence": {"size": "1Gi", "storageClass": ""},
        },
        "netcheck": {
            "image": IMAGE_DEFAULTS["netcheck"],
            "enabled": True,
        },
        "init": {
            "image": IMAGE_DEFAULTS["init"],
        },
        "coordinatorBootstrap": {
            "image": IMAGE_DEFAULTS["coordinatorBootstrap"],
        },
        "createBucket": {
            "image": IMAGE_DEFAULTS["createBucket"],
        },
        "exportClientConfig": {
            "image": {
                "repository": "bitnami/kubectl",
                "tag": "latest",
            },
        },
    }
    return values


def process(input_dir, output_dir, env_example_path):
    """Main processing pipeline."""
    templates_in = os.path.join(input_dir, "templates")
    templates_out = os.path.join(output_dir, "templates")
    os.makedirs(templates_out, exist_ok=True)

    all_files = load_all_yamls(templates_in)

    # Separate files by type
    deployments = {}
    services = {}
    pods = {}
    pvcs = {}
    configmaps = {}

    for filename, data in all_files:
        kind = data.get("kind", "")
        service_name = get_service_name(data)

        if kind == "Deployment":
            deployments[service_name] = data
        elif kind == "Service":
            services[service_name] = data
        elif kind == "Pod":
            pods[service_name] = data
        elif kind == "PersistentVolumeClaim":
            claim_name = data.get("metadata", {}).get("name", "")
            pvcs[claim_name] = data
        elif kind == "ConfigMap":
            configmaps[service_name] = data

    # --- Process StatefulSets ---
    for svc_name in STATEFULSET_SERVICES:
        if svc_name not in deployments:
            print(f"  WARN: {svc_name} deployment not found, skipping StatefulSet conversion")
            continue

        dep = deployments.pop(svc_name)
        value_key = get_value_key(svc_name)

        # Extract service name BEFORE cleaning labels (clean_labels removes io.kompose.service)
        clean_annotations(dep)
        clean_labels(dep)
        templatize_image(dep, value_key)
        templatize_resources(dep, value_key)
        templatize_ports(dep, value_key)

        statefulset = convert_to_statefulset(dep, pvcs, svc_name, value_key)
        out_name = f"{svc_name}-statefulset.yaml"
        dump_yaml(statefulset, os.path.join(templates_out, out_name))
        print(f"  StatefulSet: {out_name}")

        # Make the matching service headless
        if svc_name in services:
            svc_data = services.pop(svc_name)
            clean_annotations(svc_data)
            clean_labels(svc_data)
            make_headless_service(svc_data)
            templatize_service_ports(svc_data, value_key)
            out_name = f"{svc_name}-service.yaml"
            dump_yaml(svc_data, os.path.join(templates_out, out_name))
            print(f"  Service (headless): {out_name}")

    # --- Process Jobs ---
    # Skip any-sync-init: we have a hand-crafted init-job.yaml that uses
    # the published any-sync-tools image with scripts mounted as ConfigMaps
    SKIP_JOBS = {"any-sync-init"}

    for svc_name, hook_config in JOB_SERVICES.items():
        if svc_name in SKIP_JOBS:
            pods.pop(svc_name, None)
            print(f"  Job: {svc_name} — skipped (hand-crafted template)")
            continue

        if svc_name not in pods:
            print(f"  WARN: {svc_name} pod not found, skipping Job conversion")
            continue

        pod = pods.pop(svc_name)
        value_key = get_value_key(svc_name)

        clean_annotations(pod)
        clean_labels(pod)
        templatize_image(pod, value_key)

        job = convert_to_job(pod, svc_name)
        # Clean labels on the job too
        clean_labels(job)

        out_name = f"{svc_name}-job.yaml"
        dump_yaml(job, os.path.join(templates_out, out_name))
        print(f"  Job: {out_name}")

    # --- Process remaining Deployments ---
    for svc_name, dep in deployments.items():
        value_key = get_value_key(svc_name)

        clean_annotations(dep)
        clean_labels(dep)
        templatize_image(dep, value_key)
        templatize_resources(dep, value_key)
        templatize_ports(dep, value_key)
        templatize_secret_mounts(dep, svc_name)

        out_name = f"{svc_name}-deployment.yaml"
        dump_yaml(dep, os.path.join(templates_out, out_name))
        print(f"  Deployment: {out_name}")

    # --- Process remaining Services ---
    for svc_name, svc_data in services.items():
        if svc_name in NO_SERVICE:
            continue

        clean_annotations(svc_data)
        clean_labels(svc_data)
        templatize_service_ports(svc_data, get_value_key(svc_name))

        out_name = f"{svc_name}-service.yaml"
        dump_yaml(svc_data, os.path.join(templates_out, out_name))
        print(f"  Service: {out_name}")

    # --- Process ConfigMaps (pass through with cleanup) ---
    # Skip any-sync-init: we have a hand-crafted templatized init-env-configmap.yaml
    SKIP_CONFIGMAPS = {"any-sync-init"}
    for svc_name, cm in configmaps.items():
        if svc_name in SKIP_CONFIGMAPS:
            print(f"  ConfigMap: {svc_name} — skipped (hand-crafted template)")
            continue
        clean_annotations(cm)
        # Keep kompose labels for configmaps as they link to services
        out_name = f"{svc_name}-configmap.yaml"
        dump_yaml(cm, os.path.join(templates_out, out_name))
        print(f"  ConfigMap: {out_name}")

    # --- Write remaining PVCs that are actually referenced ---
    used_pvcs = set()
    
    # Find all referenced PVCs in StatefulSets, Deployments, and Jobs
    # We check the templates output directory directly to see what actually survived
    for root, dirs, files in os.walk(templates_out):
        for f in files:
            if not (f.endswith("-deployment.yaml") or f.endswith("-statefulset.yaml") or f.endswith("-job.yaml")):
                continue
            with open(os.path.join(root, f), 'r') as fh:
                content = fh.read()
            for claim_name in pvcs.keys():
                if f"claimName: {claim_name}" in content:
                    used_pvcs.add(claim_name)

    for claim_name, pvc_data in pvcs.items():
        if claim_name not in used_pvcs:
            continue
        clean_annotations(pvc_data)
        out_name = f"{claim_name}-pvc.yaml"
        dump_yaml(pvc_data, os.path.join(templates_out, out_name))
        print(f"  PVC: {out_name}")

    # --- Generate values.yaml ---
    values = generate_values(env_example_path)
    dump_yaml(values, os.path.join(output_dir, "values.yaml"))
    print(f"  values.yaml generated")

    # --- Write Chart.yaml ---
    chart = {
        "apiVersion": "v2",
        "name": "any-sync",
        "description": "Helm chart for Anytype any-sync self-hosted infrastructure",
        "version": "0.1.0",
        "appVersion": "0.11.1",
        "keywords": ["anytype", "any-sync", "self-hosted", "p2p"],
        "home": "https://github.com/anyproto/any-sync-dockercompose",
        "sources": ["https://github.com/anyproto/any-sync-dockercompose"],
    }
    dump_yaml(chart, os.path.join(output_dir, "Chart.yaml"))
    print(f"  Chart.yaml generated")


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(script_dir)

    input_dir = os.path.join(repo_root, ".tmp-chart")
    output_dir = os.path.join(repo_root, "charts", "any-sync")
    env_example = os.path.join(repo_root, ".env.example")

    if not os.path.isdir(input_dir):
        print(f"ERROR: Input directory not found: {input_dir}")
        print("Run 'kompose convert -c -o .tmp-chart' first.")
        sys.exit(1)

    print(f"Processing kompose output: {input_dir}")
    print(f"Output chart directory: {output_dir}")
    process(input_dir, output_dir, env_example)
    print("Done.")


if __name__ == "__main__":
    main()
