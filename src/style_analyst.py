import re
import json
import logging
from pathlib import Path
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)


class StyleAnalyst:
    """
    Analyses a book's style and builds a glossary by sending the first
    N chapters to the Gemini API via two specialised prompts:

      1. style_prompt   → produces a Markdown stylistic profile.
      2. glossary_prompt → produces a machine-ready JSON glossary.

    Both outputs are merged into a single Analysis Markdown file that the
    Translator will later use as its style-and-glossary reference.
    """

    def __init__(self, config) -> None:
        self.cfg = config
        self.client = genai.Client(api_key=self.cfg.API_KEY)

    # ------------------------------------------------------------------ #
    #  Public entry point                                                  #
    # ------------------------------------------------------------------ #

    def run(self) -> None:
        """Execute the full analysis pipeline."""
        logger.info("Reading '%s'...", self.cfg.BOOK_NAME)
        book_text = self._load_file(self.cfg.MARKDOWN_PATH)

        logger.info(
            "Selecting the first %d chapter(s) for analysis...",
            self.cfg.ANALYSIS_CHAPTERS,
        )
        sample = self._select_chapters(book_text)

        logger.info("Building analysis prompts...")
        prompt_style = self._build_prompt(self.cfg.STYLE_PROMPT_PATH, sample)
        prompt_glossary = self._build_prompt(self.cfg.GLOSSARY_PROMPT_PATH, sample)

        logger.info("Gemini is analysing writing style...")
        style_analysis = self._call_api(prompt_style, response_format="text")

        logger.info("Gemini is extracting the glossary...")
        glossary_raw = self._call_api(prompt_glossary, response_format="json")

        self._validate_glossary(glossary_raw)
        self._save_analysis(style_analysis, glossary_raw)
        logger.info("Analysis saved to '%s'.", self.cfg.ANALYSIS_PATH)

    # ------------------------------------------------------------------ #
    #  Private helpers                                                     #
    # ------------------------------------------------------------------ #

    def _load_file(self, file_path: str) -> str:
        """Read a UTF-8 text file and return its content."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        return path.read_text(encoding="utf-8")

    def _select_chapters(self, content: str) -> str:
        """
        Split on Markdown H2 headings and return the first
        cfg.ANALYSIS_CHAPTERS chapters joined as a single string.
        """
        chapters = [c.strip() for c in re.split(r"(?=\n##)", content) if c.strip()]

        if not chapters:
            raise ValueError("No chapters (## headings) found in the Markdown file.")

        selected = chapters[: self.cfg.ANALYSIS_CHAPTERS]
        logger.debug("Selected %d / %d chapters.", len(selected), len(chapters))
        return "\n\n".join(selected)

    def _build_prompt(self, prompt_path: str, sample_text: str) -> str:
        """Append the chapter sample to the base prompt template."""
        base = self._load_file(prompt_path)
        return f"{base}\n{sample_text}"

    def _call_api(self, prompt: str, response_format: str = "text") -> str:
        """
        Send a prompt to the Gemini model and return the raw text response.

        Args:
            prompt:          The full prompt string.
            response_format: ``"text"`` for Markdown, ``"json"`` for JSON.
        """
        mime = "application/json" if response_format == "json" else "text/plain"
        cfg = types.GenerateContentConfig(response_mime_type=mime)

        response = self.client.models.generate_content(
            model=self.cfg.MODEL_ID,
            contents=prompt,
            config=cfg,
        )

        if not response.text:
            raise RuntimeError("Gemini returned an empty response.")

        return response.text

    def _validate_glossary(self, raw_json: str) -> None:
        """
        Attempt to parse the glossary JSON and log a warning if malformed.
        We do not raise here so the pipeline can still save the raw output.
        """
        try:
            # Strip stray markdown fences that some models add
            clean = re.sub(r"```(?:json)?|```", "", raw_json).strip()
            data = json.loads(clean)
            n_chars = len(data.get("characters", []))
            n_locs = len(data.get("locations", []))
            n_terms = len(data.get("lore_terms", []))
            logger.info(
                "Glossary validated — %d characters, %d locations, %d lore terms.",
                n_chars,
                n_locs,
                n_terms,
            )
        except json.JSONDecodeError as exc:
            logger.warning("Glossary JSON could not be parsed: %s", exc)

    def _save_analysis(self, style_analysis: str, glossary_json: str) -> None:
        """Merge style analysis and glossary into a single Markdown file."""
        output_path = Path(self.cfg.ANALYSIS_PATH)

        content = (
            style_analysis.strip()
            + "\n\n"
            + "```json\n"
            + glossary_json.strip()
            + "\n```\n"
        )

        output_path.write_text(content, encoding="utf-8")