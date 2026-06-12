from azdo_migrator.config import AppConfig
from azdo_migrator.client import AzureDevOpsClient

def get_nodes(client: AzureDevOpsClient, node_type: str) -> dict:
    # api-version 7.0 for Classification Nodes
    response = client.get(f"wit/classificationnodes/{node_type}?$depth=10&api-version=7.0")
    return response.json()

def extract_nodes(node: dict, path: str = "") -> list:
    results = []
    current_path = f"{path}/{node['name']}" if path else node['name']
    results.append({
        "name": node['name'],
        "path": current_path,
        "attributes": node.get("attributes", {})
    })
    
    for child in node.get("children", []):
        results.extend(extract_nodes(child, current_path))
        
    return results

def create_node(client: AzureDevOpsClient, node_type: str, path: str, name: str, attributes: dict):
    # Path is relative to the root node (which is the project name)
    # The API expects just the path part without the project name for the endpoint
    parts = path.split("/")
    
    # We skip the root (project) name
    if len(parts) > 1:
        parent_path = "/".join(parts[1:-1])
        endpoint_path = f"{node_type}/{parent_path}" if parent_path else node_type
    else:
        # Should not happen as we don't recreate the root
        return
        
    payload = {"name": name}
    if attributes:
        payload["attributes"] = attributes
        
    try:
        client.post(f"wit/classificationnodes/{endpoint_path}?api-version=7.0", json=payload)
        print(f"Created {node_type}: {path}")
    except Exception as e:
        print(f"Failed to create {node_type} {path}: {e}")

def sync_sprints_and_areas(config: AppConfig):
    print("Starting Sprints and Areas synchronization...")
    
    source_client = AzureDevOpsClient(config.source.org_url, config.source.project, config.source.pat)
    target_client = AzureDevOpsClient(config.target.org_url, config.target.project, config.target.pat)
    
    for node_type in ["iterations", "areas"]:
        print(f"\nFetching {node_type} from {config.source.project}...")
        try:
            source_root = get_nodes(source_client, node_type)
            nodes = extract_nodes(source_root)
            
            # Skip the root node (it already exists in the target project)
            nodes_to_create = nodes[1:]
            
            print(f"Found {len(nodes_to_create)} {node_type} to migrate.")
            
            for node in nodes_to_create:
                name = node["name"]
                path = node["path"]
                attributes = node.get("attributes", {})
                
                # We optionally strip the source project name from the path to map to the target
                # If path was "Chimera/Sprint 1", we want to create "Sprint 1" under "appLockr"
                create_node(target_client, node_type, path, name, attributes)
                
        except Exception as e:
            print(f"Error migrating {node_type}: {e}")
            
    print("\nSprints and Areas synchronization completed.")
