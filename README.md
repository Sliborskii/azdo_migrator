# Azure DevOps Migration Tool (azdo_migrator)

A comprehensive utility for full and accurate migration of projects between Azure DevOps organizations.

A key feature of this tool is its ability to not just "copy" data, but to **retroactively fix** historical artifacts:
- Fix "phantom" users (whose email domains have changed).
- Download and re-upload inline images from task descriptions.
- Fix broken links to tasks (including `#123` mentions).
- Replace absolute links to Wiki pages with working dynamic links.
- Perform bulk replacements of cross-links within the Wiki Markdown files themselves.

## 1. Preparation (Prerequisites)

1. **Python 3.9+**
2. Clone the repository and install dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. Create `config.json` based on `config.example.json`. You will need:
   - **Source PAT** (Personal Access Token) from the old Azure DevOps.
   - **Target PAT** from the new Azure DevOps.
   > The tokens must have **Read & Write** permissions for Work Items, Identity, and Graph.

## 2. Step 1: Base Migration

At this stage, we migrate the structure and the tasks themselves.

1. **Sync Sprints and Area Paths:**
   ```bash
   python -m azdo_migrator.cli --config config.json --sync-sprints
   ```

2. **Migrate all Work Items:**
   ```bash
   python -m azdo_migrator.cli --config config.json --sync-workitems
   ```
   > [!WARNING]
   > Executing this command creates a `migration_state.json` file, which contains a "map" of old IDs to new task IDs. **Do not delete it!** It is strictly required for all subsequent fixes.

## 3. Step 2: Post-Migration Fixes

At the time of task creation, the system does not yet know all the links (since some tasks have not been created yet). Furthermore, employee email domains might have changed.

### A) Fix Assignees (Users)
1. **Generate User Mapping:**
   ```bash
   python -m azdo_migrator.cli --config config.json --generate-users
   ```
   This will fetch lists of people from the old and new Graph APIs and create `user_mapping.json`.
2. **Manual Review:** Open `user_mapping.json`. Users for whom the system found no match in the new ADO will be marked as `null`. Manually enter a valid email of a new employee (or your own email) to whom you want to assign these tasks.
3. **Apply Assignees:**
   ```bash
   python -m azdo_migrator.cli --config config.json --fix-users
   ```

### B) Fix Links, Images, and Mentions
Run these three commands sequentially to "clean up" the text in descriptions and comments:
```bash
# Fixes user mentions (@Name)
python -m azdo_migrator.cli --config config.json --fix-mentions

# Downloads images from old ADO and uploads to the new one
python -m azdo_migrator.cli --config config.json --fix-images

# Fixes cross-links to tasks (incl. #123) and links to the Wiki
python -m azdo_migrator.cli --config config.json --fix-links
```

## 4. Step 3: Wiki Migration

Since the Wiki in Azure DevOps is a standard Git repository, we migrate it via Git, but we "fix" the Markdown files first.

1. Clone the old Wiki to your computer:
   ```bash
   git clone https://dev.azure.com/OLD_ORG/OLD_PROJ/_git/OLD_PROJ.wiki
   ```
2. Point our built-in script at this folder:
   ```bash
   python -m azdo_migrator.cli --config config.json --fix-wiki-repo /path/to/cloned/folder
   ```
   > [!NOTE]
   > The script uses your `migration_state.json` and the old ADO API to find all `#123` mentions and absolute `_wiki/wikis/.../Settings` URL links in the Markdown files, replacing them with new valid links. Thus, **cross-links between the Wiki and tasks work in both directions!**
3. Push the result to the new Wiki:
   ```bash
   cd /path/to/cloned/folder
   git remote add target https://dev.azure.com/NEW_ORG/NEW_PROJ/_git/NEW_PROJ.wiki
   git push target main
   ```

## Quick Start

If you are confident that `user_mapping.json` will be generated perfectly, you can run the entire pipeline (except the Wiki) with one command:
```bash
python -m azdo_migrator.cli --config config.json --all
```
However, it is recommended to go through the steps sequentially to control the migration quality.
