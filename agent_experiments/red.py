#!/usr/bin/env python3

from pdfminer.high_level import extract_text
import sys
import os

def pdf_to_text(pdf_path: str, output_path: str = None):
    # Auto-generate output filename if none provided
    if output_path is None:
        base = os.path.splitext(pdf_path)[0]
        output_path = f"{base}.txt"

    # Extract text from the PDF
    text = extract_text(pdf_path)

    # Write to text file
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(text)

    return output_path

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python pdf_to_text.py <input.pdf> [output.txt]")
        sys.exit(1)

    pdf_file = sys.argv[1]
    out_file = sys.argv[2] if len(sys.argv) > 2 else None

    result = pdf_to_text(pdf_file, out_file)
    print(f"Text extracted to: {result}")
