import argparse
import sys

from azdo_migrator.config import load_config
from azdo_migrator.steps.sprints import sync_sprints_and_areas
from azdo_migrator.steps.workitems import sync_workitems
from azdo_migrator.steps.mentions import fix_mentions
from azdo_migrator.steps.images import fix_inline_images
from azdo_migrator.steps.links import fix_inline_links
from azdo_migrator.steps.users import generate_user_mapping, fix_users
from azdo_migrator.steps.wiki import fix_wiki_repo

def main():
    parser = argparse.ArgumentParser(description="Azure DevOps Migration CLI Tool")
    parser.add_argument("--config", type=str, required=True, help="Path to the JSON configuration file")
    
    parser.add_argument("--sync-sprints", action="store_true", help="Sync Sprints and Area Paths")
    parser.add_argument("--sync-workitems", action="store_true", help="Sync Work Items (includes comments, attachments, etc.)")
    parser.add_argument("--fix-mentions", action="store_true", help="Retroactively fix user mentions in HTML")
    parser.add_argument("--fix-images", action="store_true", help="Retroactively fix inline images in HTML")
    parser.add_argument("--fix-links", action="store_true", help="Retroactively fix inline work item links in HTML")
    parser.add_argument("--generate-users", action="store_true", help="Generate user_mapping.json based on source and target ADO users")
    parser.add_argument("--fix-users", action="store_true", help="Fix user assignments on migrated items using user_mapping.json")
    parser.add_argument("--fix-wiki-repo", type=str, help="Path to the cloned wiki repository to fix absolute URLs and work item references")
    parser.add_argument("--all", action="store_true", help="Run all migration steps sequentially (Warning: bypasses manual user mapping review!)")
    parser.add_argument("--debug-item", type=int, help="Debug a specific missing work item by ID")
    
    args = parser.parse_args()
    
    if not any([args.sync_sprints, args.sync_workitems, args.fix_mentions, args.fix_images, args.fix_links, args.generate_users, args.fix_users, args.fix_wiki_repo, args.all, args.debug_item]):
        print("Please specify at least one action flag (e.g., --sync-workitems or --all)")
        parser.print_help()
        sys.exit(1)
        
    try:
        config = load_config(args.config)
        print("Configuration loaded successfully.")
    except Exception as e:
        print(f"Failed to load configuration: {e}")
        sys.exit(1)
        
    if args.all or args.sync_sprints:
        sync_sprints_and_areas(config)
        
    if args.all or args.sync_workitems:
        sync_workitems(config)
        
    if args.all or args.fix_mentions:
        fix_mentions(config)
        
    if args.all or args.fix_images:
        fix_inline_images(config)
        
    if args.all or args.fix_links:
        fix_inline_links(config)

    if args.all or args.generate_users:
        generate_user_mapping(config)

    if args.all or args.fix_users:
        fix_users(config)
        
    if args.all or args.fix_wiki_repo:
        wiki_dir = args.fix_wiki_repo if args.fix_wiki_repo else input("Enter path to cloned wiki repo: ")
        fix_wiki_repo(config, wiki_dir)
        
    if args.debug_item:
        from azdo_migrator.client import AzureDevOpsClient
        client = AzureDevOpsClient(config.source.org_url, config.source.project, config.source.pat)
        print(f"\nDebugging Work Item {args.debug_item} in Source Project ({config.source.project})...")
        try:
            res = client.session.get(f"{client._build_url(f'wit/workitems/{args.debug_item}?api-version=7.0')}")
            if res.status_code == 404:
                print(f"❌ Item {args.debug_item} NOT FOUND. It might be permanently deleted.")
            elif res.status_code == 200:
                data = res.json()
                print(f"✅ Found Item {args.debug_item}:")
                print(f"   Project: {data['fields'].get('System.TeamProject')}")
                print(f"   Type:    {data['fields'].get('System.WorkItemType')}")
                print(f"   State:   {data['fields'].get('System.State')}")
                
                if data['fields'].get('System.TeamProject') != config.source.project:
                    print(f"   ⚠️ WARNING: This item is in '{data['fields'].get('System.TeamProject')}', NOT '{config.source.project}'. That is why it didn't migrate.")
            else:
                print(f"❌ Error fetching item: HTTP {res.status_code} - {res.text}")
        except Exception as e:
            print(f"Exception: {e}")
        
    print("\nDone.")

if __name__ == "__main__":
    main()
