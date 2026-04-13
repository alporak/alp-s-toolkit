#!/usr/bin/env python3
import os
import re
import json
from pathlib import Path

# --- Configuration & Defaults ---
CONFIG_FILE = '.project_dumper_config.json'
DEFAULT_CONFIG = {
    'max_depth': 3,
    'output_file': 'project_dump.txt',
    'entry_file': ''
}

# --- Parsing Engines ---
# Matches function definitions: ReturnType Name(Args) {
C_FUNC_DEF = re.compile(r'^[\w\s\*]+\s+([\w]+)\s*\([^)]*\)\s*\{', re.MULTILINE)
# Matches Structs, Enums, Typedefs
C_TYPE_DEF = re.compile(r'^(typedef\s+)?(struct|enum|union)\s*[\w]*\s*\{[\s\S]*?\}\s*[\w]*\s*;', re.MULTILINE)
C_SIMPLE_TYPEDEF = re.compile(r'^typedef\s+[\w\s\*]+\s+[\w]+\s*;', re.MULTILINE)

def strip_comments(code):
    """Removes C-style comments while preserving strings."""
    def replacer(match):
        s = match.group(0)
        if s.startswith('/'): return " "
        else: return s
    pattern = re.compile(
        r'//.*?$|/\*.*?\*/|\'(?:\\.|[^\\\'])*\'|"(?:\\.|[^\\"])*"',
        re.DOTALL | re.MULTILINE
    )
    return re.sub(pattern, replacer, code)

def clean_whitespace(code):
    """Minimizes whitespace for token efficiency."""
    code = re.sub(r'\n\s*\n', '\n', code)
    return "\n".join(line.rstrip() for line in code.splitlines() if line.strip())

class CParser:
    @staticmethod
    def get_blocks(content):
        """Splits C code into headers, types, and named function bodies."""
        content = strip_comments(content)
        blocks = {'headers': [], 'types': [], 'functions': {}, 'defines': []}
        
        for line in content.splitlines():
            line = line.strip()
            if line.startswith('#include'): blocks['headers'].append(line)
            if line.startswith('#define'): blocks['defines'].append(line)

        for match in C_TYPE_DEF.finditer(content):
            blocks['types'].append(match.group(0))
        for match in C_SIMPLE_TYPEDEF.finditer(content):
            blocks['types'].append(match.group(0))

        for match in C_FUNC_DEF.finditer(content):
            func_name = match.group(1)
            start_idx = match.start()
            brace_count, end_idx = 0, -1
            for i in range(start_idx, len(content)):
                if content[i] == '{': brace_count += 1
                elif content[i] == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end_idx = i + 1
                        break
            if end_idx != -1:
                blocks['functions'][func_name] = content[start_idx:end_idx]
        return blocks

    @staticmethod
    def find_usages(content):
        """Extracts potential function/macro symbols from a string."""
        return set(re.findall(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\b', content))

def resolve_path(base_file, import_str, all_files):
    """Finds the physical file for an include string."""
    import_path = Path(import_str)
    stem = import_path.stem
    
    candidates = [
        base_file.parent / import_str,
        base_file.parent / f"{stem}.c",
        base_file.parent / f"{stem}.cpp",
        Path("include") / import_str,
        Path("src") / import_str,
        Path("lib") / import_str
    ]
    for c in candidates:
        try:
            resolved = c.resolve()
            if resolved in all_files: return resolved
        except: continue
    return None

def load_config():
    config = DEFAULT_CONFIG.copy()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                saved = json.load(f)
                config.update(saved)
        except: pass
    return config

def main():
    config = load_config()
    all_files = {}
    
    # 1. Index Project
    for root, dirs, files in os.walk('.'):
        dirs[:] = [d for d in dirs if d not in {'.git', 'node_modules', 'obj', 'bin', 'build'}]
        for f in files:
            p = Path(root) / f
            try: all_files[p.resolve()] = p
            except: pass

    print("--- Project Surgical Dumper ---")
    
    entry_input = input(f"Entry file [{config.get('entry_file')}]: ").strip() or config.get('entry_file')
    if not entry_input or not os.path.exists(entry_input):
        print(f"Error: File '{entry_input}' not found.")
        return
    
    entry_path = Path(entry_input).resolve()
    max_depth = int(input(f"Search depth [{config['max_depth']}]: ") or config['max_depth'])
    out_file = input(f"Output file [{config['output_file']}]: ") or config['output_file']

    # Update config
    config.update({'entry_file': entry_input, 'max_depth': max_depth, 'output_file': out_file})
    with open(CONFIG_FILE, 'w') as f: json.dump(config, f)

    # 2. Dependency Collection
    processed_files = {} # Path -> Blocks
    used_symbols = set()
    queue = [(entry_path, 0)]
    visited = set()

    print(f"Analyzing {entry_path.name} and dependencies...")

    while queue:
        curr_path, depth = queue.pop(0)
        if curr_path in visited or depth > max_depth: continue
        visited.add(curr_path)

        with open(curr_path, 'r', encoding='utf-8', errors='ignore') as f:
            raw_content = f.read()
            blocks = CParser.get_blocks(raw_content)
            processed_files[curr_path] = blocks
            
            # Entry file: assume all symbols in it are "used"
            if curr_path == entry_path:
                processed_files[curr_path]['is_entry'] = True
                used_symbols.update(CParser.find_usages(raw_content))
            
            # Extract includes to find new files
            includes = re.findall(r'#include\s*[<"]([^>"]+)[>"]', strip_comments(raw_content))
            for inc in includes:
                res = resolve_path(curr_path, inc, all_files)
                if res and res not in visited:
                    queue.append((res, depth + 1))

    # 3. Iterative Symbol Resolution 
    # (If a used function uses another function, keep expanding)
    changed = True
    while changed:
        count_before = len(used_symbols)
        for path, blocks in processed_files.items():
            for name, body in blocks['functions'].items():
                if name in used_symbols:
                    # This function is used, so any symbols it calls are also used
                    used_symbols.update(CParser.find_usages(body))
        changed = len(used_symbols) > count_before

    # 4. Export
    with open(out_file, 'w', encoding='utf-8') as out:
        for path, blocks in sorted(processed_files.items()):
            try: rel = path.relative_to(os.getcwd())
            except: rel = path
            
            out.write(f"\n// --- FILE: {rel} ---\n")
            for h in blocks['headers']: out.write(h + "\n")
            for d in blocks['defines']: out.write(d + "\n")
            for t in blocks['types']: out.write(clean_whitespace(t) + "\n")
            
            for name, body in blocks['functions'].items():
                # Export if it's the main file OR if the function is actually called elsewhere
                if blocks.get('is_entry') or name in used_symbols:
                    out.write(clean_whitespace(body) + "\n")

    print(f"Successfully exported to {out_file} ({os.path.getsize(out_file):,} bytes)")

if __name__ == "__main__":
    main()