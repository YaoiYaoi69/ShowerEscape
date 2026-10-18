import re


EMOTIONS = frozenset({"happy", "scared", "angry", "surprised", "embarrassed"})
TAG_PATTERN = re.compile(r"\{([^{}]+)\}")
SENTENCE_END_PATTERN = re.compile(r"[.!?]+[\"']?")
TRAILING_TAG_PATTERN = re.compile(r"\s*\{([^{}]+)\}\s*$")
BARE_EMOTION_PATTERN = re.compile(
    r"\s+(happy|scared|angry|surprised|embarrassed)\s*$",
    re.IGNORECASE,
)


def parse_emotion_tags(response: str) -> tuple[str, list[str]]:
    """Split a tagged response into clean display text and ordered emotion values."""
    tags = [match.group(1) for match in TAG_PATTERN.finditer(response)]
    unknown = [tag for tag in tags if tag not in EMOTIONS]
    if unknown:
        raise ValueError(f"Unknown emotion tag(s): {', '.join(unknown)}")
    if not tags:
        raise ValueError("The response contains no emotion tags.")
    display_text = TAG_PATTERN.sub("", response)
    display_text = re.sub(r"[ \t]+([.!?])", r"\1", display_text)
    display_text = re.sub(r" {2,}", " ", display_text).strip()
    return display_text, tags


def validate_tagged_response(response: str) -> list[str]:
    """Require one valid trailing emotion tag for every sentence."""
    if not TAG_PATTERN.search(response):
        raise ValueError("Assistant responses must include an emotion tag.")

    tags = []
    position = 0
    while response[position:].strip():
        sentence_end = SENTENCE_END_PATTERN.search(response, position)
        if sentence_end is None:
            raise ValueError("Every sentence must end with punctuation and an emotion tag.")
        sentence = response[position:sentence_end.end()].strip()
        if not sentence:
            raise ValueError("Emotion tags must follow a sentence.")

        tag_match = re.match(
            r"\s*\{([^{}]+)\}",
            response[sentence_end.end():],
        )
        if tag_match is None:
            raise ValueError("Every sentence must have its own trailing emotion tag.")
        tag = tag_match.group(1)
        if tag not in EMOTIONS:
            raise ValueError(f"Unknown emotion tag: {{{tag}}}")
        tags.append(tag)
        position = sentence_end.end() + tag_match.end()

    return tags


def normalize_tagged_response(response: str) -> str:
    """Canonicalize a trailing bare emotion into a tag on each sentence."""
    try:
        validate_tagged_response(response)
    except ValueError as original_error:
        trailing_tag = TRAILING_TAG_PATTERN.search(response)
        if trailing_tag is not None:
            emotion = trailing_tag.group(1)
            text = response[:trailing_tag.start()].rstrip()
        else:
            bare_emotion = BARE_EMOTION_PATTERN.search(response)
            if bare_emotion is None:
                raise original_error
            emotion = bare_emotion.group(1).lower()
            text = response[:bare_emotion.start()].rstrip()
        if emotion not in EMOTIONS:
            raise ValueError(f"Unknown emotion tag: {{{emotion}}}")
    else:
        return response

    parts = []
    position = 0
    while position < len(text):
        sentence_end = SENTENCE_END_PATTERN.search(text, position)
        if sentence_end is None:
            raise ValueError("Every sentence must end with punctuation.")
        sentence = text[position:sentence_end.end()].strip()
        tag_match = re.match(r"\s*\{([^{}]+)\}", text[sentence_end.end():])
        if tag_match is None:
            parts.append(f"{sentence} {{{emotion}}}")
        else:
            tag = tag_match.group(1)
            if tag not in EMOTIONS:
                raise ValueError(f"Unknown emotion tag: {{{tag}}}")
            parts.append(f"{sentence} {{{tag}}}")
            position = sentence_end.end() + tag_match.end()
            continue
        position = sentence_end.end()

    normalized = " ".join(parts)
    validate_tagged_response(normalized)
    return normalized
