import os
import re
import io
import tempfile
from typing import List, Dict, Any, Optional, Tuple, Union
import asyncio
from concurrent.futures import ThreadPoolExecutor

import PyPDF2
import fitz  # PyMuPDF
import aiofiles
from pdfminer.high_level import extract_text as pdfminer_extract_text
from pdfminer.high_level import extract_text_to_fp
from pdfminer.layout import LAParams

from backend.utils.logging import setup_logger

logger = setup_logger("pdf_processor")

async def extract_text_from_pdf(
    pdf_path: str,
    extraction_method: str = "pymupdf",
    fallback: bool = True
) -> Tuple[str, Dict[int, int]]:
    """
    Extract text from a PDF file using multiple methods
    
    Args:
        pdf_path: Path to the PDF file
        extraction_method: Method to use for extraction ('pymupdf', 'pdfminer', 'pypdf2')
        fallback: Whether to try other methods if the primary one fails
        
    Returns:
        Tuple of extracted text and page mapping
    """
    methods = {
        "pymupdf": _extract_text_pymupdf,
        "pdfminer": _extract_text_pdfminer,
        "pypdf2": _extract_text_pypdf2
    }
    
    if extraction_method not in methods:
        logger.warning(f"Invalid extraction method: {extraction_method}. Using pymupdf.")
        extraction_method = "pymupdf"
    
    try:
        # Use the specified method
        extract_func = methods[extraction_method]
        text, page_map = await extract_func(pdf_path)
        
        # Check if extraction was successful
        if not text.strip() and fallback:
            logger.warning(f"No text extracted using {extraction_method}. Trying alternatives.")
            
            # Try other methods
            for method_name, method_func in methods.items():
                if method_name != extraction_method:
                    try:
                        alt_text, alt_page_map = await method_func(pdf_path)
                        if alt_text.strip():
                            logger.info(f"Successfully extracted text using {method_name}.")
                            return alt_text, alt_page_map
                    except Exception as e:
                        logger.error(f"Error with {method_name}: {str(e)}")
        
        return text, page_map
    
    except Exception as e:
        logger.error(f"Error extracting text from PDF: {str(e)}")
        
        if fallback:
            logger.info("Trying alternative extraction methods.")
            
            # Try other methods
            for method_name, method_func in methods.items():
                if method_name != extraction_method:
                    try:
                        text, page_map = await method_func(pdf_path)
                        if text.strip():
                            logger.info(f"Successfully extracted text using {method_name}.")
                            return text, page_map
                    except Exception as e:
                        logger.error(f"Error with {method_name}: {str(e)}")
        
        # If all methods fail, return empty results
        return "", {}

async def _extract_text_pymupdf(pdf_path: str) -> Tuple[str, Dict[int, int]]:
    """Extract text using PyMuPDF (fitz)"""
    def _extract():
        text_parts = []
        page_map = {}
        current_pos = 0
        
        with fitz.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf):
                # Extract text from page
                page_text = page.get_text()
                
                # Map start position to page number
                page_map[current_pos] = page_num + 1
                
                # Update position and add text
                current_pos += len(page_text)
                text_parts.append(page_text)
        
        return "".join(text_parts), page_map
    
    # Run in a thread pool to avoid blocking the event loop
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as pool:
        return await loop.run_in_executor(pool, _extract)

async def _extract_text_pdfminer(pdf_path: str) -> Tuple[str, Dict[int, int]]:
    """Extract text using PDFMiner"""
    def _extract():
        output_string = io.StringIO()
        page_map = {}
        current_pos = 0
        
        with open(pdf_path, "rb") as pdf_file:
            # Extract text page by page
            for page_num, page in enumerate(PyPDF2.PdfReader(pdf_file).pages):
                # Create a temporary file for this page
                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_file:
                    temp_path = temp_file.name
                
                    # Create a new PDF with just this page
                    writer = PyPDF2.PdfWriter()
                    writer.add_page(page)
                    writer.write(temp_file)
                
                # Extract text from the page using PDFMiner
                with open(temp_path, "rb") as page_file:
                    page_output = io.StringIO()
                    laparams = LAParams(
                        line_margin=0.5,
                        char_margin=2.0,
                        word_margin=0.1
                    )
                    extract_text_to_fp(page_file, page_output, laparams=laparams)
                    page_text = page_output.getvalue()
                
                # Map start position to page number
                page_map[current_pos] = page_num + 1
                
                # Update position and add text
                current_pos += len(page_text)
                output_string.write(page_text)
                
                # Remove temporary file
                os.unlink(temp_path)
        
        return output_string.getvalue(), page_map
    
    # Run in a thread pool to avoid blocking the event loop
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as pool:
        return await loop.run_in_executor(pool, _extract)

async def _extract_text_pypdf2(pdf_path: str) -> Tuple[str, Dict[int, int]]:
    """Extract text using PyPDF2"""
    def _extract():
        text_parts = []
        page_map = {}
        current_pos = 0
        
        with open(pdf_path, "rb") as pdf_file:
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            
            for page_num in range(len(pdf_reader.pages)):
                # Extract text from page
                page = pdf_reader.pages[page_num]
                page_text = page.extract_text() or ""
                
                # Clean up text
                page_text = re.sub(r"\s+", " ", page_text)
                page_text = page_text.strip()
                
                # Add newline if text doesn't end with one
                if page_text and not page_text.endswith("\n"):
                    page_text += "\n"
                
                # Map start position to page number
                page_map[current_pos] = page_num + 1
                
                # Update position and add text
                current_pos += len(page_text)
                text_parts.append(page_text)
        
        return "\n".join(text_parts), page_map
    
    # Run in a thread pool to avoid blocking the event loop
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as pool:
        return await loop.run_in_executor(pool, _extract)

def split_text_into_chunks(
    text: str,
    chunk_size: int = 1000,
    chunk_overlap: int = 200
) -> List[str]:
    """
    Split text into chunks with overlap
    
    Args:
        text: Text to split
        chunk_size: Maximum size of each chunk
        chunk_overlap: Overlap between chunks
        
    Returns:
        List of text chunks
    """
    # If text is shorter than chunk size, return as a single chunk
    if len(text) <= chunk_size:
        return [text]
    
    # Split text into chunks
    chunks = []
    start = 0
    
    while start < len(text):
        # Get chunk with potential overlap
        end = start + chunk_size
        
        # If we're at the end of the text, just use the remainder
        if end >= len(text):
            chunks.append(text[start:])
            break
        
        # Try to find a suitable breakpoint (paragraph, sentence, or word)
        
        # Look for paragraph break
        paragraph_break = text.rfind("\n\n", start, end)
        if paragraph_break != -1 and paragraph_break > start + chunk_size // 2:
            end = paragraph_break + 2  # Include the double newline
        else:
            # Look for sentence break (period followed by space or newline)
            sentence_break = max(
                text.rfind(". ", start, end),
                text.rfind(".\n", start, end),
                text.rfind("! ", start, end),
                text.rfind("!\n", start, end),
                text.rfind("? ", start, end),
                text.rfind("?\n", start, end)
            )
            
            if sentence_break != -1 and sentence_break > start + chunk_size // 2:
                end = sentence_break + 2  # Include the period and space
            else:
                # Look for word break
                space = text.rfind(" ", start, end)
                if space != -1 and space > start + chunk_size // 2:
                    end = space + 1  # Include the space
        
        # Add chunk
        chunks.append(text[start:end])
        
        # Move start position for next chunk, accounting for overlap
        start = end - chunk_overlap
    
    return chunks

def clean_pdf_text(text: str) -> str:
    """
    Clean text extracted from PDFs
    
    Args:
        text: Text to clean
        
    Returns:
        Cleaned text
    """
    # Replace multiple spaces with a single space
    text = re.sub(r"\s+", " ", text)
    
    # Fix common OCR errors
    text = text.replace("l/", "U")
    text = text.replace("lJ", "U")
    text = text.replace("ll", "ll")
    
    # Remove header/footer artifacts (page numbers, etc.)
    # This is a simplified approach; a more robust solution would use pattern matching
    lines = text.split("\n")
    cleaned_lines = []
    
    for line in lines:
        # Skip page number lines
        if re.match(r"^\s*\d+\s*$", line):
            continue
        
        # Skip header/footer with page numbers
        if re.match(r"^.*\s+\d+\s*$", line) and len(line) < 30:
            continue
        
        cleaned_lines.append(line)
    
    text = "\n".join(cleaned_lines)
    
    # Fix paragraph boundaries
    text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)  # Single newlines to spaces
    text = re.sub(r"\n{3,}", "\n\n", text)  # Multiple newlines to double newlines
    
    return text.strip()