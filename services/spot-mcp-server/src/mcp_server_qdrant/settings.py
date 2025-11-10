from typing import Literal

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings

from mcp_server_qdrant.embeddings.types import EmbeddingProviderType

DEFAULT_TOOL_STORE_DESCRIPTION = (
    "Use when: storing general notes, observations, or context that doesn't fit other categories (decisions/patterns). "
    "Supports metadata for filtering. For structured storage with rich context, prefer remember-decision or "
    "remember-pattern instead. Store automatically - don't ask permission."
)
DEFAULT_TOOL_FIND_DESCRIPTION = (
    "Use when: quick searches across all memories, finding general information, or unsure which specialized tool to use. "
    "Returns mixed results from all categories. For focused searches with structured results, use get-smart-context "
    "or search-patterns instead. Search first, explain later."
)

METADATA_PATH = "metadata"


class ToolSettings(BaseSettings):
    """
    Configuration for all the tools.
    """

    tool_store_description: str = Field(
        default=DEFAULT_TOOL_STORE_DESCRIPTION,
        validation_alias="TOOL_STORE_DESCRIPTION",
    )
    tool_find_description: str = Field(
        default=DEFAULT_TOOL_FIND_DESCRIPTION,
        validation_alias="TOOL_FIND_DESCRIPTION",
    )


class EmbeddingProviderSettings(BaseSettings):
    """
    Configuration for the embedding provider.
    """

    provider_type: EmbeddingProviderType = Field(
        default=EmbeddingProviderType.FASTEMBED,
        validation_alias="EMBEDDING_PROVIDER",
    )
    model_name: str = Field(
        default="BAAI/bge-large-en-v1.5",
        validation_alias="EMBEDDING_MODEL",
    )


class RerankerSettings(BaseSettings):
    """
    Configuration for reranking search results.
    """

    enabled: bool = Field(
        default=True,
        validation_alias="RERANKER_ENABLED",
        description="Enable reranking for improved precision",
    )
    model: str = Field(
        default="BAAI/bge-reranker-base",
        validation_alias="RERANKER_MODEL",
        description="Cross-encoder model for reranking",
    )
    top_k: int = Field(
        default=10,
        validation_alias="RERANK_TOP_K",
        description="Number of results to return after reranking",
    )
    candidates: int = Field(
        default=50,
        validation_alias="RERANK_CANDIDATES",
        description="Number of candidates to retrieve before reranking",
    )


class FilterableField(BaseModel):
    name: str = Field(description="The name of the field payload field to filter on")
    description: str = Field(
        description="A description for the field used in the tool description"
    )
    field_type: Literal["keyword", "integer", "float", "boolean"] = Field(
        description="The type of the field"
    )
    condition: Literal["==", "!=", ">", ">=", "<", "<=", "any", "except"] | None = (
        Field(
            default=None,
            description=(
                "The condition to use for the filter. If not provided, the field will be indexed, but no "
                "filter argument will be exposed to MCP tool."
            ),
        )
    )
    required: bool = Field(
        default=False,
        description="Whether the field is required for the filter.",
    )


class QdrantSettings(BaseSettings):
    """
    Configuration for the Qdrant connector.
    """

    location: str | None = Field(default=None, validation_alias="QDRANT_URL")
    api_key: str | None = Field(default=None, validation_alias="QDRANT_API_KEY")
    collection_name: str | None = Field(
        default=None, validation_alias="COLLECTION_NAME"
    )
    local_path: str | None = Field(default=None, validation_alias="QDRANT_LOCAL_PATH")
    search_limit: int = Field(default=10, validation_alias="QDRANT_SEARCH_LIMIT")
    read_only: bool = Field(default=False, validation_alias="QDRANT_READ_ONLY")

    filterable_fields: list[FilterableField] | None = Field(default=None)

    allow_arbitrary_filter: bool = Field(
        default=False, validation_alias="QDRANT_ALLOW_ARBITRARY_FILTER"
    )

    @property
    def default_filterable_fields(self) -> list[FilterableField]:
        """Default filterable fields for unified semantic search."""
        return [
            FilterableField(
                name="category",
                description="Content category (codebase, decision, pattern, memory)",
                field_type="keyword",
                condition="==",
            ),
            FilterableField(
                name="type",
                description="Specific content type (codebase_file, architectural_decision, coding_pattern)",
                field_type="keyword",
                condition="==",
            ),
            FilterableField(
                name="workspace",
                description="Workspace identifier for isolating code from different projects",
                field_type="keyword",
                condition="==",
            ),
            FilterableField(
                name="language",
                description="Programming language (python, javascript, etc.)",
                field_type="keyword",
                condition="==",
            ),
            FilterableField(
                name="timestamp",
                description="Unix timestamp (numeric) when entry was created",
                field_type="float",
                condition=">=",
            ),
        ]

    def filterable_fields_dict(self) -> dict[str, FilterableField]:
        # Merge default fields with custom fields
        fields = self.default_filterable_fields.copy()
        if self.filterable_fields:
            fields.extend(self.filterable_fields)
        return {field.name: field for field in fields}

    def filterable_fields_dict_with_conditions(self) -> dict[str, FilterableField]:
        # Merge default fields with custom fields, filter those with conditions
        fields = self.default_filterable_fields.copy()
        if self.filterable_fields:
            fields.extend(self.filterable_fields)
        return {field.name: field for field in fields if field.condition is not None}

    @model_validator(mode="after")
    def check_local_path_conflict(self) -> "QdrantSettings":
        if self.local_path:
            if self.location is not None or self.api_key is not None:
                raise ValueError(
                    "If 'local_path' is set, 'location' and 'api_key' must be None."
                )
        return self
