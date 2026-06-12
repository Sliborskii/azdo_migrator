import json
from azdo_migrator.config import AppConfig
from azdo_migrator.client import AzureDevOpsClient
from azdo_migrator.steps.workitems import load_state

from azdo_migrator.config import AppConfig
from azdo_migrator.client import AzureDevOpsClient
from azdo_migrator.steps.workitems import load_state

def get_users_from_org(org_url, pat):
    org_name = org_url.rstrip("/").split("/")[-1]
    url = f"https://vssps.dev.azure.com/{org_name}/_apis/graph/users?api-version=7.1-preview.1"
    import requests
    res = requests.get(url, auth=('', pat))
    if res.status_code == 200:
        return res.json().get('value', [])
    return []

def is_real_user(u):
    email = (u.get('mailAddress') or u.get('principalName') or '').lower()
    name = (u.get('displayName') or '').lower()
    return 'service' not in name and '@' in email

def generate_user_mapping(config: AppConfig):
    print("Fetching users from Azure DevOps Graph API...")
    source_users = get_users_from_org(config.source.org_url, config.source.pat)
    target_users = get_users_from_org(config.target.org_url, config.target.pat)

    source_real = [u for u in source_users if is_real_user(u)]
    target_real = [u for u in target_users if is_real_user(u)]

    target_by_email = { (u.get('mailAddress') or u.get('principalName')).lower(): u for u in target_real }
    target_by_prefix = { (u.get('mailAddress') or u.get('principalName')).split('@')[0].lower(): u for u in target_real }
    target_by_name = { u.get('displayName').lower(): u for u in target_real if u.get('displayName') }

    mapping = {}
    for su in source_real:
        semail = (su.get('mailAddress') or su.get('principalName')).lower()
        sname = su.get('displayName', '')
        sprefix = semail.split('@')[0]
        
        tu = target_by_email.get(semail)
        if not tu:
            tu = target_by_prefix.get(sprefix)
        if not tu:
            tu = target_by_name.get(sname.lower())
            
        if not tu and 'matthew james' in sname.lower():
            tu = target_by_name.get('matt james')
            
        if tu:
            temail = (tu.get('mailAddress') or tu.get('principalName')).lower()
            mapping[semail] = temail
        else:
            mapping[semail] = None # Will require manual review

    with open("user_mapping.json", "w") as f:
        json.dump(mapping, f, indent=2)

    print("Mapping generated in 'user_mapping.json'. Please review and manually update any 'null' values before running --fix-users.")

def fix_users(config: AppConfig):
    state_file = config.options.state_file
    mapping = load_state(state_file)
    if not mapping:
        print("No migration state found. Please run migration first.")
        return
        
    try:
        with open("user_mapping.json", "r") as f:
            user_mapping = json.load(f)
    except FileNotFoundError:
        print("user_mapping.json not found. Cannot map users.")
        return
        
    source_client = AzureDevOpsClient(config.source.org_url, config.source.project, config.source.pat)
    target_client = AzureDevOpsClient(config.target.org_url, config.target.project, config.target.pat)
    
    count = 0
    for chimera_id, applockr_id in mapping.items():
        if config.options.limit and count >= config.options.limit:
            break
            
        try:
            # Fetch source item to get the true Assigned To
            source_wi = source_client.get(f"wit/workitems/{chimera_id}?api-version=7.0").json()
            assigned_to = source_wi.get("fields", {}).get("System.AssignedTo", {})
            
            # ADO identity field can be an object or string
            source_email = None
            if isinstance(assigned_to, dict):
                source_email = assigned_to.get("uniqueName") or assigned_to.get("descriptor")
            elif isinstance(assigned_to, str) and assigned_to:
                # E.g. "Name <email>"
                if "<" in assigned_to and ">" in assigned_to:
                    source_email = assigned_to.split("<")[1].split(">")[0]
                else:
                    source_email = assigned_to
                    
            if not source_email:
                continue
                
            source_email = source_email.lower()
            target_email = user_mapping.get(source_email)
            
            if not target_email:
                target_email = "hanna.aliaksandrava@alcore.tech" # Fallback just in case
                
            patch_doc = [{
                "op": "replace",
                "path": "/fields/System.AssignedTo",
                "value": target_email
            }]
            
            # Fetch target item to see if it's already assigned correctly
            target_wi = target_client.get(f"wit/workitems/{applockr_id}?api-version=7.0").json()
            target_assigned_to = target_wi.get("fields", {}).get("System.AssignedTo", {})
            
            already_correct = False
            if isinstance(target_assigned_to, dict):
                if target_assigned_to.get("uniqueName", "").lower() == target_email.lower():
                    already_correct = True
                    
            if not already_correct:
                if not target_assigned_to:
                    patch_doc[0]["op"] = "add"
                    
                target_client.patch(f"wit/workitems/{applockr_id}?bypassRules=true&api-version=7.0", json=patch_doc, is_json_patch=True)
                print(f"Updated AppLockr WI {applockr_id} assigned to -> {target_email}")
                count += 1
                
        except Exception as e:
            print(f"Error processing Chimera WI {chimera_id} -> AppLockr {applockr_id}: {e}")

    print(f"Done! Processed {count} work items for user assignments.")
