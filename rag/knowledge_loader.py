import re
from dataclasses import dataclass
from pathlib import Path

SECTION_HEADER = re.compile(r"^=+\s*(.+?)\s*=+$", re.MULTILINE)
TRIGGER_PREFIX = "This section answers:"


@dataclass(frozen=True)
class KnowledgeSection:
    section_id: str
    title: str
    triggers: tuple[str, ...]
    content: str
    source_file: str

    @property
    def embedding_text(self) -> str:
        parts = [self.title]
        if self.triggers:
            parts.append(", ".join(self.triggers))
        parts.append(self.content)
        return "\n\n".join(parts)

    @property
    def display_text(self) -> str:
        header = f"=== {self.title} ==="
        if self.triggers:
            trigger_line = f"{TRIGGER_PREFIX} {', '.join(self.triggers)}"
            return f"{header}\n{trigger_line}\n{self.content}"
        return f"{header}\n{self.content}"


def _slugify(title: str, index: int) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return f"{index:02d}-{slug[:80]}"


def load_knowledge_sections(source_path: Path) -> list[KnowledgeSection]:
    if not source_path.is_file():
        raise FileNotFoundError(f"Knowledge source not found: {source_path}")

    text = source_path.read_text(encoding="utf-8")
    matches = list(SECTION_HEADER.finditer(text))
    if not matches:
        raise ValueError(f"No sections found in knowledge source: {source_path}")

    sections: list[KnowledgeSection] = []
    for index, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[start:end].strip()

        triggers: tuple[str, ...] = ()
        content = body

        if body.startswith(TRIGGER_PREFIX):
            lines = body.splitlines()
            trigger_line = lines[0][len(TRIGGER_PREFIX) :].strip()
            triggers = tuple(
                trigger.strip()
                for trigger in trigger_line.split(",")
                if trigger.strip()
            )
            content = "\n".join(lines[1:]).strip()

        sections.append(
            KnowledgeSection(
                section_id=_slugify(title, index),
                title=title,
                triggers=triggers,
                content=content,
                source_file=source_path.name,
            )
        )

    return sections
