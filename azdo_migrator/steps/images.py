import re
from urllib.parse import urlparse, parse_qs
from azdo_migrator.config import AppConfig
from azdo_migrator.client import AzureDevOpsClient
from azdo_migrator.steps.workitems import load_state

def find_chimera_urls(text: str) -> list:
    if not text:
        return []
    # Match src="..." pointing to chimerabeta attachments
    # We use a non-greedy match that just looks for the generic dev.azure.com path
    pattern = r'src="(https://dev\.azure\.com/[^"]+?/_apis/wit/attachments/[^"]+?)"'
    return re.findall(pattern, text)

def fix_inline_images(config: AppConfig):
    print("Starting inline images synchronization...")
    source_client = AzureDevOpsClient(config.source.org_url, config.source.project, config.source.pat)
    target_client = AzureDevOpsClient(config.target.org_url, config.target.project, config.target.pat)
    
    state_file = config.options.state_file
    id_mapping = load_state(state_file)
    if not id_mapping:
        print("No migration state found. Nothing to update.")
        return

    text_fields_to_check = [
        "System.Description",
        "System.History",
        "Microsoft.VSTS.TCM.ReproSteps",
        "Acceptance Criteria"
    ]
    
    url_map = {}
    print(f"Checking {len(id_mapping)} migrated items for inline images...")

    count = 0
    for chimera_id_str, applockr_id in id_mapping.items():
        if config.options.limit and count >= config.options.limit:
            break
            
        try:
            wi = source_client.get(f"wit/workitems/{chimera_id_str}?api-version=7.0").json()
            fields = wi.get("fields", {})
            comments = target_client.get(f"wit/workitems/{applockr_id}/comments?api-version=7.0-preview.3").json().get('comments', [])
            
            urls_to_download = set()
            for field in text_fields_to_check:
                if field in fields:
                    urls_to_download.update(find_chimera_urls(fields[field]))
            for comment in comments:
                urls_to_download.update(find_chimera_urls(comment.get("text", "")))
                
            for old_url in urls_to_download:
                if old_url in url_map:
                    continue
                    
                # Download
                content = source_client.session.get(old_url).content
                # Upload
                parsed_url = urlparse(old_url)
                qs = parse_qs(parsed_url.query)
                filename = qs.get("fileName", ["image.png"])[0]
                
                # Must use target_client's org_url
                upload_url = f"{target_client.org_url}/{target_client.project}/_apis/wit/attachments?fileName={filename}&api-version=7.0"
                res = target_client.session.post(upload_url, data=content, headers={"Content-Type": "application/octet-stream"})
                res.raise_for_status()
                url_map[old_url] = res.json()['url']
                
            # Patch WI Text Fields
            patch_doc = []
            target_wi = target_client.get(f"wit/workitems/{applockr_id}?api-version=7.0").json()
            target_fields = target_wi.get("fields", {})
            
            for field in text_fields_to_check:
                if field in target_fields:
                    text = target_fields[field]
                    changed = False
                    for old_url, new_url in url_map.items():
                        if old_url in text:
                            text = text.replace(old_url, new_url)
                            changed = True
                    if changed:
                        patch_doc.append({
                            "op": "replace",
                            "path": f"/fields/{field}",
                            "value": text
                        })
                        
            if patch_doc:
                target_client.patch(f"wit/workitems/{applockr_id}?bypassRules=true&api-version=7.0", json=patch_doc, is_json_patch=True)
                print(f"  Updated image fields for AppLockr WI {applockr_id}")
                
            # Patch Comments
            for comment in comments:
                text = comment.get("text", "")
                changed = False
                for old_url, new_url in url_map.items():
                    if old_url in text:
                        text = text.replace(old_url, new_url)
                        changed = True
                if changed:
                    target_client.patch(f"wit/workitems/{applockr_id}/comments/{comment['id']}?api-version=7.0-preview.3", json={"text": text})
                    print(f"  Updated comment {comment['id']} for AppLockr WI {applockr_id}")
                    
        except Exception as e:
            print(f"Error processing images for Chimera WI {chimera_id_str} -> AppLockr {applockr_id}: {e}")
            
        count += 1
            
    print("Inline images fix completed.")
