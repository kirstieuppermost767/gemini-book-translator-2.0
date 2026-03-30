import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Config:
    BOOK_NAME: str = "book_sample"
    INPUT_PDF: str = ""
    CHAPTERS_TO_TRANSLATE: int | None = None
    
    # Generated 
    MARKDOWN_PATH: str = ""
    ANALYSIS_PATH: str = ""
    TRANSLATED_PATH: str = ""
    
    # Prompts
    PROMPTS_DIR: str = "prompts/"
    STYLE_PROMPT_PATH: str = f"{PROMPTS_DIR}style_prompt.txt"
    GLOSSARY_PROMPT_PATH: str = f"{PROMPTS_DIR}glossary_prompt.txt"
    TRANSLATION_PROMPT_PATH: str = f"{PROMPTS_DIR}translation_prompt.txt"
    
    # Model
    API_KEY: str | None = field(default_factory=lambda: os.getenv('GEMINI_API_KEY'))
    MODEL_ID: str = 'gemini-3.1-flash-lite-preview'
    
    # Parameters pipeline
    ANALYSIS_CHAPTERS: int = 2
    HEADER_MIN_SIZE: float = 18.0 
    MARGIN_TOP: float = 60.0
    MARGIN_BOTTOM: float = 780.0
    SKIP_PAGES: set = field(default_factory=lambda: set())
    API_SLEEP_SECONDS: int = 5

    def __post_init__(self):
        """Dynamically generates paths based on the book title."""
        if not self.INPUT_PDF:
            self.INPUT_PDF = f"{self.BOOK_NAME}.pdf"
            
        self.MARKDOWN_PATH = f"{self.BOOK_NAME} - Markdown.md"
        self.ANALYSIS_PATH = f"{self.BOOK_NAME} - Analysis.md"
        self.TRANSLATED_PATH = f"{self.BOOK_NAME} - Translated.md"