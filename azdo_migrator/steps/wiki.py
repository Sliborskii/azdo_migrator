import os
import re
import urllib.parse
from azdo_migrator.config import AppConfig
from azdo_migrator.client import AzureDevOpsClient
from azdo_migrator.steps.workitems import load_state

def fix_wiki_repo(config: AppConfig, wiki_dir: str):
    state_file = config.options.state_file
    mapping = load_state(state_file)
    mapping = {str(k): str(v) for k, v in mapping.items()}
    
    if not mapping:
        print("Empty migration state. Proceeding anyway just in case.")

    source_client = AzureDevOpsClient(config.source.org_url, config.source.project, config.source.pat)
    source_proj = config.source.project
    target_org = config.target.org_url.rstrip("/")
    target_proj = config.target.project
    
    pattern = re.compile(r'#(\d+)')
    url_pattern = re.compile(r'https://dev\.azure\.com/[^/]+/[^/]+/_workitems/edit/(\d+)/?')
    wiki_pattern = re.compile(r'https://dev\.azure\.com/[^/]+/[^/]+/_wiki/wikis/[^/]+/(\d+)/[^\s"\'<>)]+')

    wiki_path_cache = {}

    count = 0
    for root, dirs, files in os.walk(wiki_dir):
        if '.git' in dirs:
            dirs.remove('.git')
            
        for file in files:
            if file.endswith('.md'):
                path = os.path.join(root, file)
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                original_content = content
                
                def id_replacer(match):
                    old_id = match.group(1)
                    if old_id in mapping:
                        return f"#{mapping[old_id]}"
                    return match.group(0)
                
                def url_replacer(match):
                    old_id = match.group(1)
                    if old_id in mapping:
                        return f"{target_org}/{target_proj}/_workitems/edit/{mapping[old_id]}"
                    return match.group(0)
                    
                def wiki_replacer(match):
                    old_wiki_id = match.group(1)
                    if old_wiki_id not in wiki_path_cache:
                        res = source_client.get(f"wiki/wikis/{source_proj}.wiki/pages/{old_wiki_id}?api-version=7.0")
                        if res.status_code == 200:
                            wiki_path_cache[old_wiki_id] = res.json().get('path')
                        else:
                            wiki_path_cache[old_wiki_id] = None
                            
                    true_path = wiki_path_cache.get(old_wiki_id)
                    if true_path:
                        encoded_path = urllib.parse.quote(true_path)
                        return f"{target_org}/{target_proj}/_wiki/wikis/{target_proj}?pagePath={encoded_path}"
                    return match.group(0)
                
                content = pattern.sub(id_replacer, content)
                content = url_pattern.sub(url_replacer, content)
                content = wiki_pattern.sub(wiki_replacer, content)
                
                if content != original_content:
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    print(f"Updated: {os.path.relpath(path, wiki_dir)}")
                    count += 1
                    
    print(f"\nDone! Updated {count} markdown files.")
