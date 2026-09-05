from pathlib import Path


PERSONA_FILES = {
    "example": "persona.txt",
    "classic": "persona_classic.txt",
    "personal": "persona_personal.txt",
}


def load_persona(name: str) -> str:
    filename = PERSONA_FILES.get(name, PERSONA_FILES["classic"])
    return Path(__file__).with_name(filename).read_text(encoding="utf-8")


def adapt_persona(name: str, tone_instruction: str) -> str:
    """Combine a persona profile with a tone selected for one chat."""
    return f"{load_persona(name)}\n\n## Current tone\n{tone_instruction}"


def available_personas() -> str:
    return ", ".join(PERSONA_FILES)
