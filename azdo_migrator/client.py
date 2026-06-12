import base64
import requests
from typing import Any, Dict, Optional

class AzureDevOpsClient:
    def __init__(self, org_url: str, project: str, pat: str):
        self.org_url = org_url.rstrip("/")
        self.project = project
        self.pat = pat
        self.session = requests.Session()
        
        # Set default authorization header
        encoded_pat = base64.b64encode(f":{self.pat}".encode()).decode()
        self.session.headers.update({
            "Authorization": f"Basic {encoded_pat}",
            "Content-Type": "application/json"
        })

    def _build_url(self, endpoint: str) -> str:
        if endpoint.startswith("http"):
            return endpoint
        return f"{self.org_url}/{self.project}/_apis/{endpoint.lstrip('/')}"

    def get(self, endpoint: str, params: Optional[Dict[str, Any]] = None, **kwargs) -> requests.Response:
        url = self._build_url(endpoint)
        response = self.session.get(url, params=params, **kwargs)
        response.raise_for_status()
        return response

    def post(self, endpoint: str, json: Optional[Dict[str, Any]] = None, data: Any = None, **kwargs) -> requests.Response:
        url = self._build_url(endpoint)
        response = self.session.post(url, json=json, data=data, **kwargs)
        response.raise_for_status()
        return response

    def patch(self, endpoint: str, json: Any, is_json_patch: bool = False, **kwargs) -> requests.Response:
        url = self._build_url(endpoint)
        headers = {}
        if is_json_patch:
            headers["Content-Type"] = "application/json-patch+json"
        
        response = self.session.patch(url, json=json, headers=headers, **kwargs)
        response.raise_for_status()
        return response
