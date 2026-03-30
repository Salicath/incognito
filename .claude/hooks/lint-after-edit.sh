#!/bin/bash
# Runs ruff on Python files after Edit/Write tool calls.
# Receives hook JSON on stdin from Claude Code.

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

# Only lint Python files
if [[ "$FILE_PATH" =~ \.py$ ]]; then
  ruff check --quiet "$FILE_PATH" 2>/dev/null
fi

exit 0
