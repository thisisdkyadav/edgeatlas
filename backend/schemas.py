from typing import Literal
from pydantic import BaseModel, Field, field_validator

class MemoryInput(BaseModel):
    title: str = Field(min_length=3, max_length=150)
    body: str = Field(min_length=10, max_length=12000)
    category: Literal['Procedure', 'Observation', 'Incident', 'Reference'] = 'Observation'
    site: str = Field(default='North station', max_length=100)
    tags: list[str] = Field(default_factory=list, max_length=12)
    visibility: Literal['local', 'team'] = 'local'
    priority: Literal['low', 'normal', 'high', 'critical'] = 'normal'
    source: str = Field(default='Field note', max_length=300)
    ttl_days: int = Field(default=0, ge=0, le=3650)
    expected_version: int | None = None

    @field_validator('title', 'body', 'site', 'source')
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError('This field cannot be blank.')
        return value.strip()

    @field_validator('tags')
    @classmethod
    def clean_tags(cls, value):
        if any(len(t) > 40 for t in value):
            raise ValueError('Tags must be at most 40 characters.')
        return list(dict.fromkeys(t.strip().lower() for t in value if t.strip()))

class SearchInput(BaseModel):
    query: str = Field(min_length=2, max_length=1000)
    mode: Literal['hybrid', 'semantic', 'keyword'] = 'hybrid'
    category: str = ''
    visibility: str = ''
    site: str = ''
    limit: int = Field(default=8, ge=1, le=30)

class ResolveInput(BaseModel):
    choice: Literal['local', 'cloud', 'merge']
    merged_body: str = Field(default='', max_length=12000)

class ConnectionInput(BaseModel):
    online: bool
    metered: bool = False

class PolicyInput(BaseModel):
    metered_min_priority: int = Field(default=70, ge=0, le=100)
    auto_sync: bool = True
