from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from opencc import OpenCC

from musicpilot.core.artist import split_artist_credit

TrackVariant = Literal[
    "live",
    "remix",
    "acoustic",
    "instrumental",
    "karaoke",
    "demo",
]
VariantEvidenceSource = Literal["title", "artist", "album", "file_name", "directory"]
VariantEvidenceStrength = Literal["strong", "weak"]

_T2S = OpenCC("t2s")
_SEARCH_TITLE_TRANSLATION = str.maketrans(
    {
        "妳": "你",
        "祢": "你",
        "裏": "里",
        "裡": "里",
        "麽": "么",
    }
)
_BRACKET_RE = re.compile(r"\[[^\]]*\]|\([^)]*\)|【[^】]*】")
_BRACKET_CAPTURE_RE = re.compile(
    r"(?P<full>\[(?P<square>[^\]]*)\]|\((?P<round>[^)]*)\)|【(?P<cjk>[^】]*)】)"
)
_DASH_SUFFIX_RE = re.compile(r"\s*[-–—:]\s*(?P<suffix>[^-–—:]+)\s*$")
_COLLAB_RE = re.compile(
    r"(?:^|\s)(?:feat(?:uring)?|ft)\.?\s+(?P<artists>.+)$",
    re.IGNORECASE,
)
_WITH_COLLAB_RE = re.compile(r"^with\s+(?P<artists>.+)$", re.IGNORECASE)
_COLLAB_MARKER_RE = re.compile(r"合唱|对唱|\bduet\b", re.IGNORECASE)
_COLLAB_SUFFIX_RE = re.compile(
    r"\s*(?:合唱版|对唱版|duet\s+version)\s*$",
    re.IGNORECASE,
)
_TITLE_COLLAB_SUFFIX_RE = re.compile(
    r"\s+(?:feat(?:uring)?|ft)\.?\s+(?P<artists>.+?)\s*$",
    re.IGNORECASE,
)
_EXPLICIT_VERSION_SUFFIX_RE = re.compile(
    r"\s+(?P<suffix>"
    r"(?:live|remix(?:ed)?|acoustic|unplugged|instrumental|karaoke|demo)"
    r"(?:\s+(?:version|ver\.?))?"
    r")\s*$",
    re.IGNORECASE,
)
_CHINESE_VERSION_SUFFIXES: tuple[tuple[re.Pattern[str], TrackVariant], ...] = (
    (re.compile(r"\s*(?:演唱会现场版|演唱会版|现场版)\s*$", re.IGNORECASE), "live"),
    (re.compile(r"\s*(?:不插电版|木吉他版)\s*$", re.IGNORECASE), "acoustic"),
    (re.compile(r"\s*(?:混音版)\s*$", re.IGNORECASE), "remix"),
    (re.compile(r"\s*(?:纯音乐版|伴奏版)\s*$", re.IGNORECASE), "instrumental"),
    (re.compile(r"\s*(?:卡拉OK版|KTV版)\s*$", re.IGNORECASE), "karaoke"),
    (re.compile(r"\s*(?:Demo版|小样版)\s*$", re.IGNORECASE), "demo"),
)
_VARIANT_PATTERNS: tuple[tuple[TrackVariant, tuple[re.Pattern[str], ...]], ...] = (
    (
        "live",
        (
            re.compile(r"\blive\b", re.IGNORECASE),
            re.compile(r"现场|演唱会", re.IGNORECASE),
        ),
    ),
    (
        "remix",
        (
            re.compile(r"\bremix(?:ed)?\b", re.IGNORECASE),
            re.compile(r"混音", re.IGNORECASE),
        ),
    ),
    (
        "acoustic",
        (
            re.compile(r"\bacoustic\b|\bunplugged\b", re.IGNORECASE),
            re.compile(r"不插电|木吉他", re.IGNORECASE),
        ),
    ),
    (
        "instrumental",
        (
            re.compile(r"\binstrumental\b", re.IGNORECASE),
            re.compile(r"伴奏|纯音乐", re.IGNORECASE),
        ),
    ),
    (
        "karaoke",
        (
            re.compile(r"\bkaraoke\b|\bktv\b", re.IGNORECASE),
            re.compile(r"卡拉\s*OK", re.IGNORECASE),
        ),
    ),
    (
        "demo",
        (
            re.compile(r"\bdemo\b", re.IGNORECASE),
            re.compile(r"小样", re.IGNORECASE),
        ),
    ),
)
_STRONG_LIVE_ALBUM_RE = re.compile(
    r"\blive\s+(?:at|from|in)\b|演唱会|现场实录|现场录音",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class TrackVariantEvidence:
    variant: str
    source: VariantEvidenceSource
    strength: VariantEvidenceStrength
    raw_value: str


@dataclass(frozen=True, slots=True)
class TrackVariantSignature:
    base_title: str
    normalized_base_title: str
    strong_variants: frozenset[TrackVariant]
    weak_variants: frozenset[TrackVariant]
    artist_credits: tuple[str, ...]
    collaboration: bool
    evidence: tuple[TrackVariantEvidence, ...]

    @property
    def artist_credit_keys(self) -> tuple[str, ...]:
        values: set[str] = set()
        for item in self.artist_credits:
            normalized = normalize_track_match_text(item)
            if normalized:
                values.add(normalized)
        return tuple(sorted(values))


@dataclass(frozen=True, slots=True)
class _ParsedTitle:
    base_title: str
    variants: frozenset[TrackVariant]
    collaborators: tuple[str, ...]
    collaboration: bool
    evidence: tuple[TrackVariantEvidence, ...]


def build_track_variant_signature(
    *,
    title: str | None,
    artist: str | None = None,
    album: str | None = None,
    file_name: str | Path | None = None,
    directories: tuple[str | Path, ...] = (),
) -> TrackVariantSignature:
    parsed_title = _parse_title(title, source="title")
    evidence = list(parsed_title.evidence)
    strong_variants = set(parsed_title.variants)
    weak_variants: set[TrackVariant] = set()

    credits = list(split_artist_credit(artist))
    collaborators = list(parsed_title.collaborators)
    collaboration = len(credits) > 1 or parsed_title.collaboration
    if len(credits) > 1:
        evidence.append(
            TrackVariantEvidence(
                variant="feat",
                source="artist",
                strength="strong",
                raw_value=str(artist or "").strip(),
            )
        )
    _extend_unique_credits(credits, collaborators)

    if file_name:
        file_stem = Path(str(file_name)).stem
        parsed_file = _parse_title(file_stem, source="file_name")
        strong_variants.update(parsed_file.variants)
        evidence.extend(parsed_file.evidence)
        if parsed_file.collaboration:
            collaboration = True
            _extend_unique_credits(credits, parsed_file.collaborators)

    album_text = _normalized_text(album)
    if album_text:
        album_variants = _detect_variants(album_text)
        if "live" in album_variants and _STRONG_LIVE_ALBUM_RE.search(album_text):
            strong_variants.add("live")
            evidence.append(
                TrackVariantEvidence(
                    variant="live",
                    source="album",
                    strength="strong",
                    raw_value=album_text,
                )
            )
            album_variants.discard("live")
        for variant in sorted(album_variants):
            weak_variants.add(variant)
            evidence.append(
                TrackVariantEvidence(
                    variant=variant,
                    source="album",
                    strength="weak",
                    raw_value=album_text,
                )
            )

    for directory in directories:
        directory_text = Path(str(directory)).name.strip()
        for variant in sorted(_detect_variants(directory_text)):
            weak_variants.add(variant)
            evidence.append(
                TrackVariantEvidence(
                    variant=variant,
                    source="directory",
                    strength="weak",
                    raw_value=directory_text,
                )
            )

    return TrackVariantSignature(
        base_title=parsed_title.base_title,
        normalized_base_title=normalize_track_match_text(parsed_title.base_title),
        strong_variants=frozenset(strong_variants),
        weak_variants=frozenset(weak_variants),
        artist_credits=tuple(credits),
        collaboration=collaboration,
        evidence=_unique_evidence(evidence),
    )


def normalize_track_match_text(value: str | None) -> str:
    if not value:
        return ""
    text = unicodedata.normalize("NFKC", value)
    text = _BRACKET_RE.sub(" ", text)
    text = _T2S.convert(text).translate(_SEARCH_TITLE_TRANSLATION)
    text = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", text)
    return text.casefold()


def variant_sort_score(
    reference: TrackVariantSignature,
    candidate: TrackVariantSignature,
) -> int:
    score = 3 if reference.strong_variants == candidate.strong_variants else -3
    if not reference.weak_variants and not candidate.weak_variants:
        return score
    reference_all = reference.strong_variants | reference.weak_variants
    candidate_all = candidate.strong_variants | candidate.weak_variants
    weak_supports_match = bool(
        reference.weak_variants & candidate_all
        or candidate.weak_variants & reference_all
    )
    return score + (1 if weak_supports_match else -1)


def strong_variants_match(
    reference: TrackVariantSignature,
    candidate: TrackVariantSignature,
) -> bool:
    return reference.strong_variants == candidate.strong_variants


def _parse_title(
    value: str | None,
    *,
    source: Literal["title", "file_name"],
) -> _ParsedTitle:
    original = _normalized_text(value)
    if not original:
        return _ParsedTitle("", frozenset(), (), False, ())
    cleaned = original
    variants: set[TrackVariant] = set()
    collaborators: list[str] = []
    collaboration = False
    evidence: list[TrackVariantEvidence] = []

    for match in tuple(_BRACKET_CAPTURE_RE.finditer(original)):
        content = next(
            (
                item
                for item in (
                    match.group("square"),
                    match.group("round"),
                    match.group("cjk"),
                )
                if item is not None
            ),
            "",
        ).strip()
        content_variants = _detect_variants(content)
        content_collaborators = _extract_collaborators(content, allow_with=True)
        content_collaboration = bool(content_collaborators) or bool(
            _COLLAB_MARKER_RE.search(content)
        )
        if not content_variants and not content_collaboration:
            continue
        collaboration = collaboration or content_collaboration
        variants.update(content_variants)
        _extend_unique_credits(collaborators, content_collaborators)
        evidence.extend(
            TrackVariantEvidence(variant, source, "strong", content)
            for variant in sorted(content_variants)
        )
        if content_collaboration:
            evidence.append(TrackVariantEvidence("feat", source, "strong", content))
        cleaned = cleaned.replace(match.group("full"), " ")

    collab_suffix = _TITLE_COLLAB_SUFFIX_RE.search(cleaned)
    if collab_suffix is not None:
        suffix = collab_suffix.group(0).strip()
        suffix_collaborators = _extract_collaborators(suffix, allow_with=False)
        if suffix_collaborators:
            collaboration = True
            _extend_unique_credits(collaborators, suffix_collaborators)
            evidence.append(TrackVariantEvidence("feat", source, "strong", suffix))
            cleaned = cleaned[: collab_suffix.start()].rstrip()

    while True:
        suffix_match = _DASH_SUFFIX_RE.search(cleaned)
        if suffix_match is None:
            break
        suffix = suffix_match.group("suffix").strip()
        suffix_variants = _detect_variants(suffix)
        suffix_collaborators = _extract_collaborators(suffix, allow_with=True)
        suffix_collaboration = bool(suffix_collaborators) or bool(
            _COLLAB_MARKER_RE.search(suffix)
        )
        if not suffix_variants and not suffix_collaboration:
            break
        collaboration = collaboration or suffix_collaboration
        variants.update(suffix_variants)
        _extend_unique_credits(collaborators, suffix_collaborators)
        evidence.extend(
            TrackVariantEvidence(variant, source, "strong", suffix)
            for variant in sorted(suffix_variants)
        )
        if suffix_collaboration:
            evidence.append(TrackVariantEvidence("feat", source, "strong", suffix))
        cleaned = cleaned[: suffix_match.start()].rstrip()

    explicit_suffix = _EXPLICIT_VERSION_SUFFIX_RE.search(cleaned)
    if explicit_suffix is not None and re.search(
        r"\b(?:version|ver\.?)\b",
        explicit_suffix.group("suffix"),
        re.IGNORECASE,
    ):
        suffix = explicit_suffix.group("suffix").strip()
        suffix_variants = _detect_variants(suffix)
        variants.update(suffix_variants)
        evidence.extend(
            TrackVariantEvidence(variant, source, "strong", suffix)
            for variant in sorted(suffix_variants)
        )
        cleaned = cleaned[: explicit_suffix.start()].rstrip()

    for pattern, variant in _CHINESE_VERSION_SUFFIXES:
        suffix_match = pattern.search(cleaned)
        if suffix_match is None:
            continue
        suffix = suffix_match.group(0).strip()
        variants.add(variant)
        evidence.append(TrackVariantEvidence(variant, source, "strong", suffix))
        cleaned = cleaned[: suffix_match.start()].rstrip()
        break

    collab_suffix = _COLLAB_SUFFIX_RE.search(cleaned)
    if collab_suffix is not None:
        suffix = collab_suffix.group(0).strip()
        collaboration = True
        evidence.append(TrackVariantEvidence("feat", source, "strong", suffix))
        cleaned = cleaned[: collab_suffix.start()].rstrip()

    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -–—:")
    return _ParsedTitle(
        base_title=cleaned or original,
        variants=frozenset(variants),
        collaborators=tuple(collaborators),
        collaboration=collaboration,
        evidence=_unique_evidence(evidence),
    )


def _detect_variants(value: str | None) -> set[TrackVariant]:
    text = _normalized_text(value)
    if not text:
        return set()
    return {
        variant
        for variant, patterns in _VARIANT_PATTERNS
        if any(pattern.search(text) for pattern in patterns)
    }


def _extract_collaborators(value: str | None, *, allow_with: bool) -> tuple[str, ...]:
    text = _normalized_text(value)
    if not text:
        return ()
    match = _COLLAB_RE.search(text)
    if match is None and allow_with:
        match = _WITH_COLLAB_RE.search(text)
    if match is None:
        return ()
    return tuple(split_artist_credit(match.group("artists")))


def _extend_unique_credits(target: list[str], values: tuple[str, ...] | list[str]) -> None:
    seen = {normalize_track_match_text(item) for item in target if item}
    for value in values:
        name = str(value).strip()
        key = normalize_track_match_text(name)
        if not name or not key or key in seen:
            continue
        seen.add(key)
        target.append(name)


def _unique_evidence(
    values: list[TrackVariantEvidence] | tuple[TrackVariantEvidence, ...],
) -> tuple[TrackVariantEvidence, ...]:
    seen: set[tuple[str, str, str, str]] = set()
    result: list[TrackVariantEvidence] = []
    for item in values:
        key = (item.variant, item.source, item.strength, item.raw_value.casefold())
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return tuple(result)


def _normalized_text(value: str | None) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).strip()
