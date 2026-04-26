#!/usr/bin/env python3
"""
Scans Vue frontend files for potentially hardcoded strings that need translation.
Outputs the findings into a CSV file.
"""

import argparse
import csv
import os
import re
import sys

FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "src"))
OUTPUT_CSV = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "untranslated_strings.csv"))

# Regex to extract the <template> block from a .vue file
TEMPLATE_RE = re.compile(r"<template>(.*?)</template>", re.DOTALL)

# Regex to extract <script> and <script setup> blocks
SCRIPT_RE = re.compile(r"<script.*?>\s*(.*?)\s*</script>", re.DOTALL)

# Regex to find string assignments or refs in script tags.
# Matches:  = "str" | ref("str") | ( "str" ) | [ "str" ] | return "str"
SCRIPT_STRING_RE = re.compile(r"""(?:=|ref\(|\(|\[|return\s+)\s*(['"`])((?:(?!\1)[^\\]|\\.)+)\1""")

# Smarter regex to match HTML tags even if they contain > inside quotes.
# e.g., <div v-if="count > 0">
TAG_RE = re.compile(r"""<(?:"[^"]*"|'[^']*'|[^'">])*>""")

# Regex to find specific untranslated attributes.
# Negative lookbehind (?<!:) ensures we don't match data-bound attributes like :title="t('key')"
ATTR_RE = re.compile(r'(?<!:)\b(placeholder|title|alt|label)="([^"]*[a-zA-Z][^"]*)"')

# Regex to find Vue mustache interpolations {{ ... }}
MUSTACHE_RE = re.compile(r"\{\{(.*?)\}\}")

# Regex to find bound attributes (:attr="...")
BOUND_ATTR_RE = re.compile(r':\b(placeholder|title|alt|label)="([^"]+)"')

# Regex to find string literals inside mustache or attribute bindings
# Matches 'string' or "string" or `string`
BINDING_STRING_RE = re.compile(r"""(['"`])((?:(?!\1)[^\\]|\\.)+)\1""")

# Regex to check if a string looks like a function call, a property, or simple math
FUNC_CALL_RE = re.compile(r"^[a-zA-Z_$][0-9a-zA-Z_$]*\(|^[A-Z0-9_]+$|^\d+$")


def is_valid_string(text):
    """Filter out noise like pure whitespace, numbers, symbols, technical constants, or single characters."""
    text = text.strip()
    if not text:
        return False
    # Ignore strings that don't contain at least one letter
    if not any(c.isalpha() for c in text):
        return False
    # Ignore very short noise
    if len(text) <= 1:
        return False

    # Specific technical exact matches to ignore
    ignore_list = {"IR2MQTT", "ON", "OFF", "PRESS", "bps", "ms", "s", "x", "px", "EVT", "OUT", "IN"}
    if text in ignore_list:
        return False

    # Ignore pure uppercase strings without spaces (likely payloads or constants)
    if text.isupper() and " " not in text:
        return False

    return True


def scan_file(filepath):
    findings = []
    with open(filepath, encoding="utf-8") as f:
        content = f.read()

    # We primarily care about .vue files and their templates
    if filepath.endswith(".vue"):
        template_match = TEMPLATE_RE.search(content)
        if template_match:
            template = template_match.group(1)

            # 1. Search for Text Nodes & Mustache bindings
            text_content = TAG_RE.sub("|||", template)

            for raw_text in text_content.split("|||"):
                # Extract and check strings inside mustache bindings {{ ... }}
                for mustache_match in MUSTACHE_RE.finditer(raw_text):
                    mustache_content = mustache_match.group(1)
                    # Ignore if the binding uses 't(' or 'i18n'
                    if "t(" in mustache_content:
                        continue

                    for string_match in BINDING_STRING_RE.finditer(mustache_content):
                        binding_str = string_match.group(2)
                        if is_valid_string(binding_str) and not FUNC_CALL_RE.match(binding_str):
                            findings.append({"Type": "Mustache Binding", "String": binding_str})

                # Remove {{ variable }} blocks to check if any static text remains
                clean_text = MUSTACHE_RE.sub("", raw_text).strip()

                if is_valid_string(clean_text):
                    # Clean up multiple whitespaces/newlines for CSV readability
                    clean_text = " ".join(clean_text.split())
                    findings.append({"Type": "Text Node", "String": clean_text})

            # 2. Search for static attributes
            for match in ATTR_RE.finditer(template):
                attr_name = match.group(1)
                attr_value = match.group(2).strip()
                if is_valid_string(attr_value):
                    findings.append({"Type": f"Attribute ({attr_name})", "String": attr_value})

            # 3. Search for dynamic bound attributes (:placeholder="..." etc)
            for match in BOUND_ATTR_RE.finditer(template):
                attr_name = match.group(1)
                attr_value = match.group(2)

                # If t( is used, it's already translated
                if "t(" in attr_value:
                    continue

                # Find literal strings inside the bound attribute
                for string_match in BINDING_STRING_RE.finditer(attr_value):
                    binding_str = string_match.group(2)
                    if is_valid_string(binding_str) and not FUNC_CALL_RE.match(binding_str):
                        findings.append({"Type": f"Bound Attribute (:{attr_name})", "String": binding_str})

        # 4. Search for strings in <script> blocks
        for script_match in SCRIPT_RE.finditer(content):
            script_content = script_match.group(1)

            # Strip out lines with t('...') to ignore already translated lines
            clean_script = "\n".join([line for line in script_content.splitlines() if "t(" not in line])

            # Find string literals in the script
            for string_match in SCRIPT_STRING_RE.finditer(clean_script):
                script_str = string_match.group(2).strip()

                # Filter out likely technical noise common in scripts (paths, basic variables, events, pure lowercase/camelCase words)
                if (
                    is_valid_string(script_str)
                    and not FUNC_CALL_RE.match(script_str)
                    and "/" not in script_str
                    and ("_" not in script_str or " " in script_str)
                    and not script_str.endswith(".vue")
                    and not script_str.endswith(".ts")
                    and " " in script_str  # In scripts, standalone words are usually variables/keys. Real sentences have spaces.
                    and "\n" not in script_str  # Filter out multi-line template literal code noise
                    and not any(char in script_str for char in "{}[]();=<>")  # Filter out code fragments that snuck into string parsing
                    and not (script_str.startswith("bg-") or script_str.startswith("text-") or script_str.startswith("border-"))  # Filter out tailwind classes
                ):
                    # Clean up multiple whitespaces
                    clean_str = " ".join(script_str.split())
                    findings.append({"Type": "Script String", "String": clean_str})

    return findings


def main():
    parser = argparse.ArgumentParser(description="Find untranslated strings in Vue files.")
    parser.add_argument("-o", "--output", help="Output CSV file path. If not provided, prints to stdout.")
    parser.add_argument("-i", "--ignore", action="append", default=[], help="Paths or directories to ignore (relative to frontend/src). Can be specified multiple times.")
    args = parser.parse_args()

    all_findings = []

    # Normalize ignore paths to absolute paths
    ignore_paths = [os.path.abspath(os.path.join(FRONTEND_DIR, p)) for p in args.ignore]

    for root, dirs, files in os.walk(FRONTEND_DIR):
        # Remove ignored directories from walk
        dirs[:] = [d for d in dirs if os.path.abspath(os.path.join(root, d)) not in ignore_paths]

        for file in files:
            if file.endswith(".vue"):
                filepath = os.path.join(root, file)

                # Check if file is ignored
                if os.path.abspath(filepath) in ignore_paths:
                    continue

                rel_path = os.path.relpath(filepath, FRONTEND_DIR)

                findings = scan_file(filepath)
                for f in findings:
                    all_findings.append([rel_path, f["Type"], f["String"]])

    if args.output:
        with open(args.output, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["File", "Type", "Hardcoded String"])
            writer.writerows(all_findings)
        print(f"✅ Scanning complete! Found {len(all_findings)} potentially hardcoded strings.")
        print(f"📄 Results saved to: {args.output}")
    else:
        writer = csv.writer(sys.stdout)
        writer.writerow(["File", "Type", "Hardcoded String"])
        writer.writerows(all_findings)


if __name__ == "__main__":
    main()
