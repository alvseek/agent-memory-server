"""The served catalog shared by MCP discovery and HTTP search."""

from typing import Literal

from munnin.content.loader import ContentLoader

CatalogKind = Literal["procedures", "resources"]


class EmptyCatalogQuery(ValueError):
    """The search phrase contains no text after normalizing separators."""


def _normalized(text: str) -> str:
    return " ".join(text.casefold().replace("-", " ").replace("_", " ").split())


def catalog_rows(
    content: ContentLoader | None, kind: CatalogKind, query: str | None = None
) -> list[dict[str, str]]:
    """List served metadata in catalog order, optionally filtering by name or title."""
    phrase = None if query is None else _normalized(query)
    if phrase == "":
        raise EmptyCatalogQuery("query must contain text, not just whitespace or separators")
    if content is None or not content.available():
        return []

    if kind == "procedures":
        content = content.metadata_snapshot()
        names, title_of, description_of = (
            content.list_prompts(), content.title_prompt, content.describe_prompt
        )
    else:
        names, title_of, description_of = (
            content.list_resources(), content.title_resource, content.describe_resource
        )

    rows = []
    for name in names:
        title = title_of(name)
        if phrase is None or phrase in _normalized(name) or phrase in _normalized(title):
            rows.append({"name": name, "title": title, "description": description_of(name)})
    return rows
