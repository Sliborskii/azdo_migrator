import json
from pathlib import Path
from pydantic import BaseModel, Field

class EnvironmentConfig(BaseModel):
    org_url: str = Field(..., description="Azure DevOps Organization URL (e.g. https://dev.azure.com/org)")
    project: str = Field(..., description="Azure DevOps Project Name")
    pat: str = Field(..., description="Personal Access Token")

class OptionsConfig(BaseModel):
    state_file: str = Field("migration_state.json", description="File to store ID mapping state")
    user_mapping_csv: str = Field("Repo migration - work items(Sheet1).csv", description="CSV file mapping users")
    limit: int | None = Field(None, description="Max number of items to process for testing")

class AppConfig(BaseModel):
    source: EnvironmentConfig
    target: EnvironmentConfig
    options: OptionsConfig = Field(default_factory=OptionsConfig)

def load_config(config_path: str) -> AppConfig:
    """Loads and validates configuration from a JSON file."""
    path = Path(config_path)
    if not path.is_file():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
        
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    return AppConfig(**data)
