"""
k8s.py — HTTP client for the kubernetes-cluster-mock.

Wraps every endpoint exposed by:
  docker run -d -p 9988:9988 ezequielmr94/kubernetes-cluster-mock:latest

The base URL is read from K8S_MOCK_URL in .env (default: http://localhost:9988).

Public API mirrors common kubectl operations:
  Pods        : list_pods, create_pod, delete_pod
  Deployments : list_deployments, create_deployment, delete_deployment
  Ingresses   : list_ingresses, create_ingress, delete_ingress
  Nodes       : list_nodes
  Custom      : change_pod_phase, change_cluster_size

ExecutorAgent in DspY.py calls k8s.execute(command) which parses a
kubectl-style command string and dispatches to the right method.
"""

import os
import json
import requests
from dotenv import load_dotenv
from typing import Any, Dict, List, Optional

load_dotenv()


class K8sClient:
    """REST client for the kubernetes-cluster-mock API."""

    def __init__(self, base_url: str = None):
        self.base_url = (base_url or os.getenv("K8S_MOCK_URL", "http://localhost:9988")).rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _get(self, path: str) -> Dict[str, Any]:
        resp = self.session.get(f"{self.base_url}{path}", timeout=10)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, body: dict = None) -> Dict[str, Any]:
        resp = self.session.post(f"{self.base_url}{path}", json=body or {}, timeout=10)
        resp.raise_for_status()
        try:
            return resp.json()
        except Exception:
            return {"status": "Success"}

    def _delete(self, path: str) -> Dict[str, Any]:
        resp = self.session.delete(f"{self.base_url}{path}", timeout=10)
        resp.raise_for_status()
        try:
            return resp.json()
        except Exception:
            return {"status": "Success"}

    # ------------------------------------------------------------------ #
    # Nodes
    # ------------------------------------------------------------------ #

    def list_nodes(self) -> List[dict]:
        """GET /api/v1/nodes"""
        data = self._get("/api/v1/nodes")
        return data.get("items", [])

    # ------------------------------------------------------------------ #
    # Pods
    # ------------------------------------------------------------------ #

    def list_pods(self, namespace: str = "production") -> List[dict]:
        """GET /api/v1/namespaces/<namespace>/pods"""
        data = self._get(f"/api/v1/namespaces/{namespace}/pods")
        return data.get("items", [])

    def list_all_pods(self) -> List[dict]:
        """GET /api/v1/pods"""
        data = self._get("/api/v1/pods")
        return data.get("items", [])

    def create_pod(self, namespace: str, name: str, image: str, labels: dict = None) -> dict:
        """POST /api/v1/namespaces/<namespace>/pods"""
        body = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": name,
                "namespace": namespace,
                "labels": labels or {"app": name},
            },
            "spec": {
                "containers": [{"name": name, "image": image}]
            },
        }
        return self._post(f"/api/v1/namespaces/{namespace}/pods", body)

    def delete_pod(self, namespace: str, name: str) -> dict:
        """DELETE /api/v1/namespaces/<namespace>/pods/<pod_name>"""
        return self._delete(f"/api/v1/namespaces/{namespace}/pods/{name}")

    # ------------------------------------------------------------------ #
    # Deployments (apps/v1)
    # ------------------------------------------------------------------ #

    def list_deployments(self, namespace: str = "production") -> List[dict]:
        """GET /apis/apps/v1/namespaces/<namespace>/deployments"""
        data = self._get(f"/apis/apps/v1/namespaces/{namespace}/deployments")
        return data.get("items", [])

    def list_all_deployments(self) -> List[dict]:
        """GET /apis/apps/v1/deployments"""
        data = self._get("/apis/apps/v1/deployments")
        return data.get("items", [])

    def create_deployment(self, namespace: str, name: str, image: str,
                          replicas: int = 1, labels: dict = None) -> dict:
        """POST /apis/apps/v1/namespaces/<namespace>/deployments"""
        lbl = labels or {"app": name}
        body = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": name, "namespace": namespace},
            "spec": {
                "replicas": replicas,
                "selector": {"matchLabels": lbl},
                "template": {
                    "metadata": {"labels": lbl},
                    "spec": {"containers": [{"name": name, "image": image}]},
                },
            },
        }
        return self._post(f"/apis/apps/v1/namespaces/{namespace}/deployments", body)

    def delete_deployment(self, namespace: str, name: str) -> dict:
        """DELETE /apis/apps/v1/namespaces/<namespace>/deployments/<name>"""
        return self._delete(f"/apis/apps/v1/namespaces/{namespace}/deployments/{name}")

    # ------------------------------------------------------------------ #
    # Ingresses (extensions/v1beta1)
    # ------------------------------------------------------------------ #

    def list_ingresses(self, namespace: str = "production") -> List[dict]:
        """GET /apis/extensions/v1beta1/namespaces/<namespace>/ingresses"""
        data = self._get(f"/apis/extensions/v1beta1/namespaces/{namespace}/ingresses")
        return data.get("items", [])

    def create_ingress(self, namespace: str, name: str, host: str,
                       service_name: str, service_port: int = 80) -> dict:
        """POST /apis/extensions/v1beta1/namespaces/<namespace>/ingresses"""
        body = {
            "apiVersion": "extensions/v1beta1",
            "kind": "Ingress",
            "metadata": {"name": name, "namespace": namespace},
            "spec": {
                "rules": [{
                    "host": host,
                    "http": {
                        "paths": [{
                            "path": "/",
                            "backend": {
                                "serviceName": service_name,
                                "servicePort": service_port,
                            },
                        }]
                    },
                }]
            },
        }
        return self._post(f"/apis/extensions/v1beta1/namespaces/{namespace}/ingresses", body)

    def delete_ingress(self, namespace: str, name: str) -> dict:
        """DELETE /apis/extensions/v1beta1/namespaces/<namespace>/ingresses/<name>"""
        return self._delete(f"/apis/extensions/v1beta1/namespaces/{namespace}/ingresses/{name}")

    # ------------------------------------------------------------------ #
    # Custom control routes
    # ------------------------------------------------------------------ #

    def change_pod_phase(self, namespace: str, pod_name: str, phase: str) -> dict:
        """POST /custom_routes/change_pod_phase/<ns>/<pod>/<phase>
        phase: Running | Pending | Succeeded | Failed | Unknown
        """
        return self._post(f"/custom_routes/change_pod_phase/{namespace}/{pod_name}/{phase}")

    def change_cluster_size(self, new_size: int) -> dict:
        """POST /custom_routes/change_cluster_size/<new_size>"""
        return self._post(f"/custom_routes/change_cluster_size/{new_size}")

    # ------------------------------------------------------------------ #
    # health-check
    # ------------------------------------------------------------------ #

    def ping(self) -> bool:
        """Return True if the mock is reachable."""
        try:
            self._get("/api/v1/nodes")
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------ #
    # execute(command) — called by ExecutorAgent in DspY.py
    # ------------------------------------------------------------------ #

    def execute(self, command: str) -> dict:
        """Parse a kubectl-style command string and call the right method.

        Supported patterns (subset of what the mock implements):
          kubectl get nodes
          kubectl get pods [-n <ns>]
          kubectl get deployments [-n <ns>]
          kubectl get ingresses [-n <ns>]
          kubectl run <name> --image=<img> [-n <ns>]
          kubectl create deployment <name> --image=<img> [-n <ns>]
          kubectl delete pod <name> [-n <ns>]
          kubectl delete deployment <name> [-n <ns>]
          kubectl delete ingress <name> [-n <ns>]

        Returns:
            {"success": bool, "output": str, "command": command}
        """
        try:
            tokens = command.strip().split()
            result = self._dispatch(tokens)
            output = json.dumps(result, indent=2) if isinstance(result, (dict, list)) else str(result)
            return {"success": True, "output": output, "command": command}
        except Exception as e:
            return {"success": False, "output": str(e), "command": command}

    def _dispatch(self, tokens: List[str]) -> Any:
        """Route a tokenised kubectl command to the right client method."""
        if not tokens or tokens[0] != "kubectl":
            raise ValueError(f"Not a kubectl command: {' '.join(tokens)}")

        # helper to extract -n / --namespace value
        def ns(default="production"):
            for flag in ("-n", "--namespace"):
                if flag in tokens:
                    idx = tokens.index(flag)
                    if idx + 1 < len(tokens):
                        return tokens[idx + 1]
            return default

        # helper to extract --image=<value>
        def image():
            for t in tokens:
                if t.startswith("--image="):
                    return t.split("=", 1)[1]
            raise ValueError("--image=<image> is required")

        verb    = tokens[1] if len(tokens) > 1 else ""
        subject = tokens[2] if len(tokens) > 2 else ""

        # ---- GET ----
        if verb == "get":
            if subject in ("nodes", "node"):
                return self.list_nodes()
            if subject in ("pods", "pod", "po"):
                return self.list_pods(ns())
            if subject in ("deployments", "deployment", "deploy"):
                return self.list_deployments(ns())
            if subject in ("ingresses", "ingress", "ing"):
                return self.list_ingresses(ns())

        # ---- RUN (creates a pod) ----
        if verb == "run":
            name = subject
            return self.create_pod(ns(), name, image())

        # ---- CREATE ----
        if verb == "create":
            if subject in ("deployment", "deploy"):
                name = tokens[3] if len(tokens) > 3 else "unnamed"
                return self.create_deployment(ns(), name, image())
            if subject in ("ingress", "ing"):
                name = tokens[3] if len(tokens) > 3 else "unnamed"
                host = next((t.split("=",1)[1] for t in tokens if t.startswith("--rule=")), f"{name}.example.com")
                return self.create_ingress(ns(), name, host, name)

        # ---- DELETE ----
        if verb == "delete":
            name = tokens[3] if len(tokens) > 3 else ""
            if subject in ("pod", "po"):
                return self.delete_pod(ns(), name)
            if subject in ("deployment", "deploy"):
                return self.delete_deployment(ns(), name)
            if subject in ("ingress", "ing"):
                return self.delete_ingress(ns(), name)

        raise ValueError(f"Unsupported kubectl command: kubectl {verb} {subject}")


# Singleton — import and use directly
k8s = K8sClient()


# ------------------------------------------------------------------ #
# Smoke-test when run directly
# ------------------------------------------------------------------ #

if __name__ == "__main__":
    print("=== k8s.py smoke-test ===")
    print(f"Connecting to: {k8s.base_url}\n")

    if not k8s.ping():
        print("✗ Mock is not running. Start it with:")
        print("  docker run -d -p 9988:9988 ezequielmr94/kubernetes-cluster-mock:latest")
        exit(1)

    print("✓ Mock is reachable\n")

    print("[1] Nodes:")
    for n in k8s.list_nodes():
        print(f"   {n['metadata']['name']}")

    print("\n[2] Create pod 'nginx-test' in namespace 'production':")
    r = k8s.create_pod("production", "nginx-test", "nginx:latest")
    print(f"   {r}")

    print("\n[3] List pods in 'production':")
    for p in k8s.list_pods("production"):
        print(f"   {p['metadata']['name']} — {p['status']['phase']}")

    print("\n[4] Change pod phase to Pending:")
    k8s.change_pod_phase("production", "nginx-test", "Pending")
    for p in k8s.list_pods("production"):
        if p["metadata"]["name"] == "nginx-test":
            print(f"   {p['metadata']['name']} — {p['status']['phase']}")

    print("\n[5] Delete pod 'nginx-test':")
    r = k8s.delete_pod("production", "nginx-test")
    print(f"   {r.get('status', r)}")

    print("\n[6] Create deployment 'web-deploy':")
    r = k8s.create_deployment("production", "web-deploy", "nginx:latest", replicas=2)
    print(f"   {r}")

    print("\n[7] List deployments:")
    for d in k8s.list_deployments("production"):
        print(f"   {d['metadata']['name']}")

    print("\n[8] execute() — kubectl-style dispatch:")
    res = k8s.execute("kubectl get pods -n production")
    print(f"   success={res['success']}")

    print("\n✓ All smoke-tests passed")
