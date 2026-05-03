from typing import Dict, List, Optional, Union

from pydantic import BaseModel, Field


# ---------- Projects ----------


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class ProjectUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class Project(BaseModel):
    id: str
    name: str
    created_at: str
    default_provider: Optional[str] = None


# ---------- Sessions ----------


class SessionCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120, default="New session")


class SessionUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class Session(BaseModel):
    id: str
    project_id: str
    title: str
    created_at: str
    updated_at: str
    provider: Optional[str] = None
    model: Optional[str] = None


class SessionModelUpdate(BaseModel):
    provider: str = Field(min_length=1, max_length=40)
    model: str = Field(min_length=1, max_length=120)


# ---------- Datasets ----------


class Dataset(BaseModel):
    id: str
    project_id: str
    filename: str
    rows: int
    columns: List[str]
    has_ohlcv: bool
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    size_bytes: int
    uploaded_at: str


class DatasetPreview(BaseModel):
    id: str
    filename: str
    columns: List[str]
    rows: int
    # Each row is a dict of column -> primitive (str/int/float/bool/None).
    sample: List[Dict[str, Union[str, int, float, bool, None]]]


# ---------- Providers ----------


class ProviderInfo(BaseModel):
    name: str
    kind: str  # "api_key" | "local" | "subscription"
    label: str
    has_credential: bool
    reachable: Optional[bool] = None
    error: Optional[str] = None
    extra: Dict[str, Union[str, int, float, bool, None]] = Field(default_factory=dict)


class ProviderKeyPayload(BaseModel):
    api_key: str = Field(min_length=1)


class OllamaConfigPayload(BaseModel):
    base_url: str = Field(min_length=1, max_length=200)


class ModelInfoDTO(BaseModel):
    id: str
    label: str
    context_window: Optional[int] = None
    description: Optional[str] = None


# ---------- App state ----------


class AppState(BaseModel):
    active_project_id: Optional[str] = None
    active_session_id: Optional[str] = None
