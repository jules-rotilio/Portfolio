"""Tag search conditions: required tags (all or any) and excluded tags."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TagQuery:
    """Which tags a file must have and must not have.

    A file matches when it has all ``include`` tags (``match_all``) or at
    least one of them (otherwise), and none of the ``exclude`` tags. An empty
    ``include`` set places no requirement, so "exclude only" queries match
    untagged files too. ``whole_catalog`` searches every indexed or tagged
    file instead of only the current folder.
    """

    include: frozenset[str] = field(default_factory=frozenset)
    exclude: frozenset[str] = field(default_factory=frozenset)
    match_all: bool = True
    whole_catalog: bool = False

    @property
    def active(self) -> bool:
        """Return whether the query filters anything."""
        return bool(self.include or self.exclude)

    def matches(self, tags: set[str] | frozenset[str]) -> bool:
        """Return whether a file with tags satisfies the query."""
        if self.exclude & tags:
            return False
        if not self.include:
            return True
        if self.match_all:
            return self.include <= tags
        return bool(self.include & tags)

    def describe(self) -> str:
        """Return a short sentence such as "all of: A, B; none of: C"."""
        parts = []
        if self.include:
            mode = "all of" if self.match_all else "any of"
            parts.append(f"{mode}: {', '.join(sorted(self.include, key=str.casefold))}")
        if self.exclude:
            parts.append(f"none of: {', '.join(sorted(self.exclude, key=str.casefold))}")
        return "; ".join(parts)
