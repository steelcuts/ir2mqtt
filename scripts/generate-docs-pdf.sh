#!/bin/sh
# Export the VitePress documentation to a single PDF.
#
# Usage: scripts/generate-docs-pdf.sh
# Output: ir2mqtt-docs.pdf (project root)
#
# Prerequisites: Node.js >= 22

set -e

ROOT_DIR="$(pwd)"

echo "▶  Installing docs dependencies..."
cd "$ROOT_DIR/docs"
npm install --silent

echo "▶  Building documentation..."
npm run build

echo "▶  Exporting to PDF..."
npm run export-pdf

echo ""
echo "✅  $(realpath "$ROOT_DIR/ir2mqtt-docs.pdf")"
