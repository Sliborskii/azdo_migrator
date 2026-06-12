import re
from azdo_migrator.config import AppConfig
from azdo_migrator.client import AzureDevOpsClient
from azdo_migrator.steps.workitems import load_state
from bs4 import BeautifulSoup

def replace_wi_links_in_text(text: str, id_mapping: dict, source_org: str, source_proj: str, target_org: str, target_proj: str, source_client: AzureDevOpsClient, wiki_path_cache: dict) -> tuple[str, bool]:
    if not text or not isinstance(text, str):
        return text, False
    
    changed = False
    
    def replacer(match):
        nonlocal changed
        url_part = match.group(1)
        old_id_str = match.group(2)
        attributes = match.group(3)
        inner_html = match.group(4)
        
        # If the old ID is in our mapping, replace it
        if old_id_str in id_mapping:
            new_id = str(id_mapping[old_id_str])
            changed = True
            
            # Replace the ID in the URL
            # Replace the ID in the inner HTML (e.g. #1176 -> #2000)
            new_inner_html = inner_html.replace(old_id_str, new_id)
            # Also visually replace the old org/project if the link text is a full URL
            new_inner_html = new_inner_html.replace(source_org, target_org).replace(source_proj, target_proj)
            
            # Also ensure the URL points to the new org/project
            new_url = f"{target_org}/{target_proj}/_workitems/edit/{new_id}"
            if url_part.endswith("/"):
                new_url += "/"
                
            return f'<a href="{new_url}"{attributes}>{new_inner_html}</a>'
            
        return match.group(0)

    # Regex matches: <a href=".../_workitems/edit/1234/?" ...>...</a>
    pattern = r'<a href="([^"]*/_workitems/edit/(\d+)/?)"([^>]*)>(.*?)</a>'
    new_text = re.sub(pattern, replacer, text)
    
    # Also fix Wiki links
    # Old URL format: https://dev.azure.com/chimerabeta/Chimera/_wiki/wikis/Chimera.wiki/410/Settings
    # New URL format: https://dev.azure.com/appLockr/appLockr/_wiki/wikis/appLockr?pagePath=/Nested/Path/To/Settings
    import urllib.parse
    
    def wiki_replacer(match):
        nonlocal changed
        old_wiki_id = match.group(1)
        
        # Resolve true path using API
        if old_wiki_id not in wiki_path_cache:
            res = source_client.get(f"wiki/wikis/{source_proj}.wiki/pages/{old_wiki_id}?api-version=7.0")
            if res.status_code == 200:
                wiki_path_cache[old_wiki_id] = res.json().get('path')
            else:
                wiki_path_cache[old_wiki_id] = None # Mark as not found
                
        true_path = wiki_path_cache.get(old_wiki_id)
        if true_path:
            changed = True
            encoded_path = urllib.parse.quote(true_path)
            return f"{target_org}/{target_proj}/_wiki/wikis/{target_proj}?pagePath={encoded_path}"
        
        return match.group(0)

    wiki_pattern = r'https://dev\.azure\.com/[^/]+/[^/]+/_wiki/wikis/[^/]+/(\d+)/[^\s"\'<>]+'
    new_text = re.sub(wiki_pattern, wiki_replacer, new_text)

    # Now replace plain text mentions like #1234 or US1234 using BeautifulSoup
    if '#' in new_text or 'US' in new_text:
        soup = BeautifulSoup(new_text, 'html.parser')
        plain_pattern = re.compile(r'#(\d+)|US(\d+)')
        soup_changed = False
        
        for text_node in soup.find_all(string=True):
            if text_node.parent and text_node.parent.name in ['style', 'script', 'a']:
                # Skip inside <a> tags just to be safe (though we already updated hrefs and their content)
                continue
                
            def plain_replacer(m):
                nonlocal soup_changed
                old_id = m.group(1) or m.group(2)
                if old_id in id_mapping:
                    soup_changed = True
                    prefix = "#" if m.group(1) else "US"
                    return f"{prefix}{id_mapping[old_id]}"
                return m.group(0)
                
            updated_text = plain_pattern.sub(plain_replacer, text_node)
            if updated_text != text_node:
                text_node.replace_with(updated_text)
                
        if soup_changed:
            new_text = str(soup)
            changed = True

    return new_text, changed

def fix_inline_links(config: AppConfig):
    print("Starting retroactive inline work item links fix...")
    target_client = AzureDevOpsClient(config.target.org_url, config.target.project, config.target.pat)
    source_client = AzureDevOpsClient(config.source.org_url, config.source.project, config.source.pat)
    
    state_file = config.options.state_file
    id_mapping = load_state(state_file)
    if not id_mapping:
        print("No migration state found. Nothing to update.")
        return

    # To string keys just in case
    id_mapping = {str(k): str(v) for k, v in id_mapping.items()}
    wiki_path_cache = {}

    text_fields_to_check = [
        "System.Description",
        "System.History",
        "Microsoft.VSTS.TCM.ReproSteps",
        "Acceptance Criteria"
    ]

    print(f"Checking {len(id_mapping)} migrated items for inline work item links...")
    target_org_stripped = config.target.org_url.rstrip("/")
    source_org_stripped = config.source.org_url.rstrip("/")

    count = 0
    for chimera_id_str, applockr_id in id_mapping.items():
        if config.options.limit and count >= config.options.limit:
            break
            
        try:
            # Fetch source item to get pristine original text
            source_wi = source_client.get(f"wit/workitems/{chimera_id_str}?api-version=7.0").json()
            source_fields = source_wi.get("fields", {})
            
            patch_doc = []
            for field in text_fields_to_check:
                if field in source_fields:
                    new_text, changed = replace_wi_links_in_text(source_fields[field], id_mapping, source_org_stripped, config.source.project, target_org_stripped, config.target.project, source_client, wiki_path_cache)
                    # We ALWAYS patch if the source field had content, to ensure we overwrite broken target state
                    # But to save API calls, we only patch if `new_text` is different from current target text
                    # Wait, it's safer to just patch if `changed` is True (meaning we found and fixed links in the source text).
                    # Actually, if the target is broken, we want to fix it. Let's fetch target fields to compare.
            
            target_wi = target_client.get(f"wit/workitems/{applockr_id}?api-version=7.0").json()
            target_fields = target_wi.get("fields", {})
            
            for field in text_fields_to_check:
                if field in source_fields:
                    new_text, changed = replace_wi_links_in_text(source_fields[field], id_mapping, source_org_stripped, config.source.project, target_org_stripped, config.target.project, source_client, wiki_path_cache)
                    if changed and new_text != target_fields.get(field):
                        patch_doc.append({
                            "op": "add" if field not in target_fields else "replace",
                            "path": f"/fields/{field}",
                            "value": new_text
                        })
                        
            if patch_doc:
                target_client.patch(f"wit/workitems/{applockr_id}?bypassRules=true&api-version=7.0", json=patch_doc, is_json_patch=True)
                print(f"  Updated fields for AppLockr WI {applockr_id}")
                
            # Fetch comments from source and target
            source_comments = source_client.get(f"wit/workitems/{chimera_id_str}/comments?api-version=7.0-preview.3").json().get('comments', [])
            target_comments = target_client.get(f"wit/workitems/{applockr_id}/comments?api-version=7.0-preview.3").json().get('comments', [])
            
            # Since we migrated them, they should be in the exact same order and count.
            # We will process the pristine source comment text and patch the target comment.
            for s_comment, t_comment in zip(source_comments, target_comments):
                new_text, changed = replace_wi_links_in_text(s_comment.get("text", ""), id_mapping, source_org_stripped, config.source.project, target_org_stripped, config.target.project, source_client, wiki_path_cache)
                if changed and new_text != t_comment.get("text", ""):
                    target_client.patch(f"wit/workitems/{applockr_id}/comments/{t_comment['id']}?api-version=7.0-preview.3", json={"text": new_text})
                    print(f"  Updated comment {t_comment['id']} in AppLockr WI {applockr_id}")
                    
        except Exception as e:
            print(f"Error processing Chimera WI {chimera_id_str} -> AppLockr {applockr_id}: {e}")
            
        count += 1
            
    print("Inline links fix completed.")
