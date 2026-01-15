#!/usr/bin/env python3
import sys

START = "<!-- Schedule Start -->"
END = "<!-- Schedule End -->"

if len(sys.argv) != 2:
    sys.exit(f"Usage: {sys.argv[0]} <markdown_file>")

with open(sys.argv[1], "r", encoding="utf-8") as f:
    text = f.read()

start_idx = text.find(START)
end_idx = text.find(END)

if start_idx == -1 or end_idx == -1 or end_idx <= start_idx:
    sys.exit("Schedule markers not found or out of order.")

start_idx += len(START)

print(text[start_idx:end_idx].strip())