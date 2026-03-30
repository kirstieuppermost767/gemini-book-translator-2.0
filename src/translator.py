import re
import time
import logging
from pathlib import Path
from google import genai
from google.genai import types
from tenacity import retry, stop_after_attempt, wait_exponential, before_sleep_log

logger = logging.getLogger(__name__)


class Translator:
    """
    Translates a Markdown book chapter by chapter using the Gemini API.

    Key features
    ------------
    - Context-aware translation: the previous chapter's Italian/English
      pair is injected into every request so the model can maintain
      stylistic consistency across chapters.
    - Automatic retry with exponential back-off (via tenacity).
    - Incremental saves: the translated file is written after every
      chapter, so progress is never lost if the pipeline is interrupted.
    - Configurable chapter range: set cfg.CHAPTERS_TO_TRANSLATE to an
      integer to limit the run, or leave it as None to translate all.
    """

    _FIRST_CHAPTER_CONTEXT = (
        "This is the first chapter — no previous translation is available. "
        "Carefully analyse all the style and glossary information provided "
        "to achieve the best possible result."
    )

    def __init__(self, config) -> None:
        self.cfg = config
        self.client = genai.Client(api_key=self.cfg.API_KEY)

    # ------------------------------------------------------------------ #
    #  Public entry point                                                  #
    # ------------------------------------------------------------------ #

    def run(self) -> None:
        """Execute the full translation pipeline."""
        logger.info("Loading source book...")
        book_text = self._load_file(self.cfg.MARKDOWN_PATH)

        logger.info("Splitting into chapters...")
        all_chapters = self._split_chapters(book_text)

        # Honour the optional chapter limit from config
        limit = self.cfg.CHAPTERS_TO_TRANSLATE
        chapters = all_chapters[:limit] if limit is not None else all_chapters
        logger.info(
            "Translating %d / %d chapter(s).", len(chapters), len(all_chapters)
        )

        logger.info("Building translation prompt...")
        base_prompt = self._build_base_prompt()

        self._translate_chapters(chapters, base_prompt)
        logger.info("Translation complete. Output: '%s'.", self.cfg.TRANSLATED_PATH)

    # ------------------------------------------------------------------ #
    #  Private helpers                                                     #
    # ------------------------------------------------------------------ #

    def _load_file(self, file_path: str) -> str:
        """Read a UTF-8 text file and return its content."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        return path.read_text(encoding="utf-8")

    def _split_chapters(self, content: str) -> list[str]:
        """Split the Markdown on H2 headings (## …)."""
        chapters = [c.strip() for c in re.split(r"(?=\n##)", content) if c.strip()]
        if not chapters:
            raise ValueError("No chapters (## headings) found in the Markdown file.")
        return chapters

    def _build_base_prompt(self) -> str:
        """
        Combine the translation prompt template with the style/glossary
        analysis produced by StyleAnalyst.
        """
        translation_prompt = self._load_file(self.cfg.TRANSLATION_PROMPT_PATH)
        style_and_glossary = self._load_file(self.cfg.ANALYSIS_PATH)
        return (
            translation_prompt.strip()
            + "\n\n# STYLE GUIDE\n"
            + style_and_glossary.strip()
        )

    def _build_chapter_prompt(
        self, base_prompt: str, chapter: str, previous_context: str
    ) -> str:
        """Assemble the full prompt for a single chapter."""
        return (
            base_prompt
            + "\n\n# REFERENCE SAMPLE\n"
            + previous_context
            + "\n\n# TEXT TO BE TRANSLATED\n"
            + chapter
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=20),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def _call_api(self, prompt: str) -> str:
        """
        Call the Gemini API with automatic retry on transient failures.
        Decorated with @retry (tenacity) — up to 3 attempts with
        exponential back-off between 4 s and 20 s.
        """
        config = types.GenerateContentConfig(response_mime_type="text/plain")
        response = self.client.models.generate_content(
            model=self.cfg.MODEL_ID,
            contents=prompt,
            config=config,
        )
        if not response.text:
            raise RuntimeError("Gemini returned an empty response.")
        return response.text

    def _append_to_output(self, text: str) -> None:
        """
        Append a translated chapter to the output file immediately.
        Creates the file on first call; appends on subsequent calls.
        """
        output_path = Path(self.cfg.TRANSLATED_PATH)
        with output_path.open("a", encoding="utf-8") as f:
            f.write(f"\n{text}")

    def _translate_chapters(self, chapters: list[str], base_prompt: str) -> None:
        """
        Core loop: translate each chapter, maintain rolling context, and
        save incrementally so progress survives interruptions.
        """
        # Reset output file at the start of a new run
        Path(self.cfg.TRANSLATED_PATH).write_text("", encoding="utf-8")

        previous_context = self._FIRST_CHAPTER_CONTEXT

        for index, chapter in enumerate(chapters, start=1):
            logger.info("Translating chapter %d / %d...", index, len(chapters))

            prompt = self._build_chapter_prompt(base_prompt, chapter, previous_context)

            try:
                translated = self._call_api(prompt)
            except Exception as exc:
                logger.error(
                    "Chapter %d failed after all retries: %s — skipping.", index, exc
                )
                # Write a visible placeholder so the gap is obvious in the output
                self._append_to_output(
                    f"\n\n> ⚠️ **Chapter {index} translation failed:** {exc}\n\n"
                )
                continue

            # Save immediately — do not wait for the full run to finish
            self._append_to_output(translated)
            logger.info("Chapter %d saved.", index)

            # Build rolling context for the next iteration
            # Truncate to ~1000 chars to stay well within prompt limits
            previous_context = (
                f"**ITALIAN:** {chapter[:1000]}\n"
                f"**TRANSLATED:** {translated[:1000]}"
            )

            # Respect the API rate limit between successful requests
            if index < len(chapters):
                time.sleep(self.cfg.API_SLEEP_SECONDS)