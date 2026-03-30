import argparse
import logging
from pathlib import Path

from src.pdf_extractor import PDFExtractor
from src.style_analyst import StyleAnalyst
from src.translator import Translator
from src.config import Config

def setup_parser() -> argparse.ArgumentParser:
    """Configures and returns the command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Automatic pipeline for literary translation with Gemini."
    )
    
    parser.add_argument(
        "-p", "--pdf",
        type=str,
        required=True,
        help="Path to the PDF file to translate (e.g., 'documents/my_book.pdf')."
    )
    
    parser.add_argument(
        "-c", "--chapters",
        type=int,
        default=None,
        help="Number of chapters to translate. If omitted, translates the entire book."
    )
    
    return parser

def main():
    # 1. Initialize the global logger to display output in the console
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S"
    )
    logger = logging.getLogger(__name__)

    # 2. Parse the arguments passed by the user
    parser = setup_parser()
    args = parser.parse_args()

    # 3. Extract the "base name" without the extension (e.g., "book.pdf" -> "book")
    book_name = Path(args.pdf).stem

    # 4. Create the configuration by injecting dynamic parameters
    cfg = Config(
        BOOK_NAME=book_name,
        INPUT_PDF=args.pdf,
        CHAPTERS_TO_TRANSLATE=args.chapters
    )
    
    logger.info(f"Starting pipeline for the book: '{cfg.BOOK_NAME}'")

    # 5. Execute the modules
    try:
        PDFExtractor(cfg).run()
        StyleAnalyst(cfg).run()
        Translator(cfg).run()
        logger.info("Pipeline completed successfully!")
    except Exception as e:
        logger.error(f"Critical error during execution: {e}")

if __name__ == "__main__":
    main()