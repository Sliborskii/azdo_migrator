import re
from azdo_migrator.config import AppConfig
from azdo_migrator.client import AzureDevOpsClient
from azdo_migrator.steps.workitems import build_user_mapping, load_state

def replace_user_mentions_in_text(text: str, applockr_by_name: dict) -> tuple[str, bool]:
    if not text or not isinstance(text, str):
        return text, False
    changed = False
    def replacer(match):
        nonlocal changed
        name = match.group(2)
        if name.lower() in applockr_by_name:
            changed = True
            new_id = applockr_by_name[name.lower()].get('originId')
            return f'<a href="#" data-vss-mention="version:2.0,{new_id}">@{name}</a>'
        return match.group(0)
    new_text = re.sub(r'<a[^>]*data-vss-mention="version:2.0,([^"]+)"[^>]*>@([^<]+)</a>', replacer, text)
    return new_text, changed

def fix_mentions(config: AppConfig):
    print("Starting retroactive mentions fix...")
    source_client = AzureDevOpsClient(config.source.org_url, config.source.project, config.source.pat)
    target_client = AzureDevOpsClient(config.target.org_url, config.target.project, config.target.pat)
    
    state_file = config.options.state_file
    id_mapping = load_state(state_file)
    if not id_mapping:
        print("No migration state found. Nothing to update.")
        return

    _, _, applockr_by_name = build_user_mapping(config, source_client, target_client)
    if not applockr_by_name:
        print("User mapping failed. Aborting.")
        return

    text_fields_to_check = [
        "System.Description",
        "System.History",
        "Microsoft.VSTS.TCM.ReproSteps",
        "Acceptance Criteria"
    ]

    print(f"Checking {len(id_mapping)} migrated items for mentions...")

    count = 0
    for chimera_id_str, applockr_id in id_mapping.items():
        if config.options.limit and count >= config.options.limit:
            break
            
        try:
            # Check fields
            wi = target_client.get(f"wit/workitems/{applockr_id}?api-version=7.0").json()
            fields = wi.get("fields", {})
            
            patch_doc = []
            for field in text_fields_to_check:
                if field in fields:
                    new_text, changed = replace_user_mentions_in_text(fields[field], applockr_by_name)
                    if changed:
                        patch_doc.append({
                            "op": "replace",
                            "path": f"/fields/{field}",
                            "value": new_text
                        })
                        
            if patch_doc:
                target_client.patch(f"wit/workitems/{applockr_id}?bypassRules=true&api-version=7.0", json=patch_doc, is_json_patch=True)
                print(f"  Updated fields for AppLockr WI {applockr_id}")
                
            # Check comments
            comments = target_client.get(f"wit/workitems/{applockr_id}/comments?api-version=7.0-preview.3").json().get('comments', [])
            for comment in comments:
                new_text, changed = replace_user_mentions_in_text(comment.get("text", ""), applockr_by_name)
                if changed:
                    target_client.patch(f"wit/workitems/{applockr_id}/comments/{comment['id']}?api-version=7.0-preview.3", json={"text": new_text})
                    print(f"  Updated comment {comment['id']} in AppLockr WI {applockr_id}")
                    
        except Exception as e:
            print(f"Error processing Chimera WI {chimera_id_str} -> AppLockr {applockr_id}: {e}")
            
        count += 1
            
    print("Mentions fix completed.")
