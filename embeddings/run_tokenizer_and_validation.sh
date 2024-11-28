#!/bin/bash

# Ensure the script exits on errors
set -e

# Define variables
TOKENIZER_SCRIPT="tokenizer.py"
VALIDATION_SCRIPT="token_validation.py"
LOCAL_DATA_DIR="C:/Users/ASUS/Desktop/LuminaLM/Data"  # Corrected path with forward slashes
TOKENIZER_OUTPUT_PATH="./medical_tokenizer.json"
VALIDATION_OUTPUT="./validation_results.txt"

# Convert Windows-style path to WSL-compatible path if necessary
if grep -qEi "(Microsoft|WSL)" /proc/version &> /dev/null; then
  LOCAL_DATA_DIR=$(wslpath "$LOCAL_DATA_DIR")
fi

# Check if the tokenizer script exists
if [[ ! -f $TOKENIZER_SCRIPT ]]; then
  echo "Error: $TOKENIZER_SCRIPT not found!"
  exit 1
fi

# Check if the validation script exists
if [[ ! -f $VALIDATION_SCRIPT ]]; then
  echo "Error: $VALIDATION_SCRIPT not found!"
  exit 1
fi

# Run the tokenizer script
echo "Running tokenizer script..."
python3 $TOKENIZER_SCRIPT --local_data_path "$LOCAL_DATA_DIR" --output_path "$TOKENIZER_OUTPUT_PATH"

# Check if the tokenizer output was created
if [[ ! -f $TOKENIZER_OUTPUT_PATH ]]; then
  echo "Error: Tokenizer output file $TOKENIZER_OUTPUT_PATH not created!"
  exit 1
fi

# Run the validation script
echo "Running validation script..."
python3 $VALIDATION_SCRIPT --tokenizer_path "$TOKENIZER_OUTPUT_PATH" > "$VALIDATION_OUTPUT"

# Check if the validation output was created
if [[ ! -f $VALIDATION_OUTPUT ]]; then
  echo "Error: Validation output file $VALIDATION_OUTPUT not created!"
  exit 1
fi

# Display success message
echo "Tokenizer creation and validation completed successfully."
echo "Tokenizer saved at: $TOKENIZER_OUTPUT_PATH"
echo "Validation results saved at: $VALIDATION_OUTPUT"
