import csv
import json
import os
import re
import time
from typing import Dict, Tuple
from azdo_migrator.config import AppConfig
from azdo_migrator.client import AzureDevOpsClient

def build_user_mapping(config: AppConfig, source_client: AzureDevOpsClient, target_client: AzureDevOpsClient) -> Tuple[Dict[str, str], Dict[str, dict], Dict[str, dict]]:
    uuid_map = {}
    applockr_by_email = {}
    applockr_by_name = {}
    
    csv_file = config.options.user_mapping_csv
    if not os.path.exists(csv_file):
        print(f"Mapping file {csv_file} not found!")
        return {}, {}, {}

    mapping = []
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            c_email = row.get('Chimera user')
            a_email = row.get('appLockr User')
            if c_email and a_email:
                mapping.append((c_email.strip(), a_email.strip()))

    print("Building user mapping...")
    
    # Target Users
    try:
        # Use Graph API endpoint for users
        url = config.target.org_url.replace("dev.azure.com", "vssps.dev.azure.com")
        res = target_client.session.get(f"{url}/_apis/graph/users?api-version=7.1-preview.1")
        res.raise_for_status()
        for u in res.json().get("value", []):
            email = u.get("mailAddress") or u.get("principalName", "")
            if email:
                applockr_by_email[email.lower()] = u
            name = u.get("displayName", "")
            if name:
                applockr_by_name[name.lower()] = u
    except Exception as e:
        print(f"Failed to fetch target users: {e}")

    # Source Users
    try:
        url = config.source.org_url.replace("dev.azure.com", "vssps.dev.azure.com")
        res = source_client.session.get(f"{url}/_apis/graph/users?api-version=7.1-preview.1")
        res.raise_for_status()
        chimera_users = res.json().get("value", [])
    except Exception as e:
        print(f"Failed to fetch source users: {e}")
        chimera_users = []

    chimera_by_email = {}
    for u in chimera_users:
        email = u.get("mailAddress") or u.get("principalName", "")
        if email:
            chimera_by_email[email.lower()] = u

    for c_email, a_email in mapping:
        c_user = chimera_by_email.get(c_email.lower())
        a_user = applockr_by_email.get(a_email.lower())
        if c_user and a_user:
            uuid_map[c_user.get('originId')] = a_user.get('originId')
            
    print(f"Mapped {len(uuid_map)} users.")
    return uuid_map, applockr_by_email, applockr_by_name

def replace_user_mentions(text: str, applockr_by_name: Dict[str, dict]) -> str:
    if not text or not isinstance(text, str):
        return text
    def replacer(match):
        name = match.group(2)
        if name.lower() in applockr_by_name:
            new_id = applockr_by_name[name.lower()].get('originId')
            return f'<a href="#" data-vss-mention="version:2.0,{new_id}">@{name}</a>'
        return match.group(0)
    return re.sub(r'<a[^>]*data-vss-mention="version:2.0,([^"]+)"[^>]*>@([^<]+)</a>', replacer, text)

def load_state(state_file: str) -> dict:
    if os.path.exists(state_file):
        with open(state_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_state(state_file: str, state: dict):
    with open(state_file, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2)

def sync_workitems(config: AppConfig):
    print("Starting Work Items synchronization...")
    source_client = AzureDevOpsClient(config.source.org_url, config.source.project, config.source.pat)
    target_client = AzureDevOpsClient(config.target.org_url, config.target.project, config.target.pat)
    
    state_file = config.options.state_file
    migration_state = load_state(state_file)
    print(f"Found {len(migration_state)} already migrated items.")

    uuid_map, applockr_by_email, applockr_by_name = build_user_mapping(config, source_client, target_client)
    
    print("Querying Source Work Items...")
    wiql = {
        "query": f"Select [System.Id] From WorkItems Where [System.TeamProject] = '{config.source.project}' Order By [System.Id] Asc"
    }
    
    try:
        res = source_client.post("wit/wiql?api-version=7.0", json=wiql)
        work_items = res.json().get("workItems", [])
    except Exception as e:
        print(f"Wiql failed: {e}")
        return

    print(f"Found {len(work_items)} work items.")
    
    if config.options.limit:
        work_items = work_items[:config.options.limit]

    for wi_ref in work_items:
        chimera_id = str(wi_ref['id'])
        if chimera_id in migration_state:
            continue
            
        print(f"\nMigrating Work Item {chimera_id}...")
        try:
            # Get full item
            wi = source_client.get(f"wit/workitems/{chimera_id}?$expand=all&api-version=7.0").json()
            
            wi_type = wi['fields']['System.WorkItemType']
            new_fields = {}
            
            # Map basic fields
            for field, value in wi['fields'].items():
                if field in ['System.Id', 'System.Rev', 'System.TeamProject', 'System.WorkItemType', 
                             'System.State', 'System.CreatedDate', 'System.ChangedDate', 'System.Watermark']:
                    continue
                
                # Replace UUIDs in text
                if isinstance(value, str):
                    value = replace_user_mentions(value, applockr_by_name)
                    
                # Fix User identities
                if isinstance(value, dict) and 'uniqueName' in value:
                    email = value.get('uniqueName', '').lower()
                    if email in applockr_by_email:
                        new_fields[field] = applockr_by_email[email].get("mailAddress")
                    continue
                    
                # Area/Iteration paths
                if field in ['System.AreaPath', 'System.IterationPath']:
                    new_fields[field] = value.replace(config.source.project, config.target.project, 1)
                    continue
                    
                new_fields[field] = value
                
            patch_doc = [{"op": "add", "path": f"/fields/{k}", "value": v} for k, v in new_fields.items()]
            
            # Create in target
            created = target_client.patch(
                f"wit/workitems/${wi_type}?bypassRules=true&api-version=7.0", 
                json=patch_doc, 
                is_json_patch=True
            ).json()
            new_id = created['id']
            print(f"  Created AppLockr WI {new_id}")
            
            # Fetch and migrate comments
            comments_res = source_client.get(f"wit/workitems/{chimera_id}/comments?api-version=7.0-preview.3").json()
            comments = comments_res.get('comments', [])
            for comment in reversed(comments):
                author = comment['createdBy']['displayName']
                text = replace_user_mentions(comment['text'], applockr_by_name)
                comment_text = f"**Original comment by {author}:**<br><br>{text}"
                target_client.post(f"wit/workitems/{new_id}/comments?api-version=7.0-preview.3", json={"text": comment_text})

            # Save state
            migration_state[chimera_id] = new_id
            save_state(state_file, migration_state)
            
        except Exception as e:
            print(f"Failed to migrate WI {chimera_id}: {e}")
            
    print("\nWork Items synchronization completed.")
