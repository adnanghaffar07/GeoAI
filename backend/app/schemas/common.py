"""Shared response shapes."""

from pydantic import BaseModel


class Page[ItemT](BaseModel):
    """Lists are always wrapped, so extra information can be added later (api-spec §1 rule 4)."""

    items: list[ItemT]
    page: int
    page_size: int
    total: int
