#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Flatten nested persona JSON file into flat interaction events (JSONL) for LightFM training."
    )
    parser.add_argument(
        "--input-file",
        required=True,
        help="Path to the nested persona JSON file (e.g. persona_full_result_000_099.json)",
    )
    parser.add_argument(
        "--output-file",
        required=True,
        help="Path where the flattened JSONL file will be written.",
    )
    args = parser.parse_args()

    input_path = Path(args.input_file).expanduser().resolve()
    output_path = Path(args.output_file).expanduser().resolve()

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    print(f"Reading nested personas from {input_path}...")
    with input_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("Input JSON must be a list of personas.")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    event_count = 0
    persona_count = 0

    print(f"Flattening and writing to {output_path}...")
    with output_path.open("w", encoding="utf-8") as out:
        for persona in data:
            persona_id = persona.get("persona_id")
            if not persona_id:
                continue
            
            persona_count += 1
            book_history = persona.get("book_history") or []
            
            for book in book_history:
                isbn = book.get("isbn")
                status = book.get("status") or "POSITIVE"
                
                if not isbn:
                    continue
                
                event = {
                    "user_id": persona_id,
                    "isbn": isbn,
                    "event_type": status.upper()
                }
                out.write(json.dumps(event, ensure_ascii=False) + "\n")
                event_count += 1

    print(f"Processing complete!")
    print(f"Total Personas processed: {persona_count}")
    print(f"Total Flattened Events written: {event_count}")


if __name__ == "__main__":
    main()
