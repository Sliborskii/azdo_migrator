# Migration Plan: Chimera Azure DevOps to Applockr Azure DevOps

## Goal
Transfer all Wiki content and Work Items from the Chimera Azure DevOps project to the Applockr Azure DevOps project.

## Approach

### 1. Wiki Migration
- Clone the wiki repository from the source project (Chimera).
- Ensure the destination project (Applockr) has a wiki provisioned.
- Clone the wiki repository from the destination project.
- Copy the content from the source wiki repo to the destination wiki repo.
- Commit and push the changes to the destination wiki repo.

### 2. Work Items Migration
- Export work items from Chimera (using Azure DevOps queries to CSV or utilizing the Azure DevOps REST API/Migration tools).
- Map user fields, state fields, and custom fields between the two projects.
- Import work items into Applockr (via CSV import or automated script).
- Verify attachments, links, and history (if supported by the migration method).

## Open Questions & Review Required
1. **Tooling:** Should we use an automated tool like `nkdAgile` (Azure DevOps Migration Tools) for work items, or a simple CSV export/import?
2. **History & Attachments:** Do we need to preserve the full revision history and attachments for the work items?
3. **Permissions:** Do we have the necessary Personal Access Tokens (PAT) and administrator rights on both Azure DevOps organizations/projects to perform these actions?

## Next Steps
Once this plan is reviewed and approved, we will begin by provisioning the necessary access tokens and setting up the migration scripts or tools.
