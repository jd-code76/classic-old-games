#!/usr/bin/env python3
"""
HTML/CSS/JS Minifier
Creates .min.html versions with minified HTML + CSS and preserved GPLv3 license
comment at top; strips comments from JS (code otherwise intact).
Usage: python3 minify_all.py <file.html|directory>
"""

import os
import sys
import argparse
import re
from pathlib import Path

# Characters after which a '/' begins a regex literal rather than division.
_REGEX_PRECEDING_CHARS = set('(,=:[!&|?{};+-*%~^')

# Keywords after which a '/' begins a regex literal rather than division.
_REGEX_PRECEDING_KEYWORDS = {
    'return', 'typeof', 'case', 'in', 'of', 'new', 'delete', 'void',
    'instanceof', 'do', 'else', 'yield'
}

# Comments containing any of these markers must never be modified or stripped.
LICENSE_COMMENT_MARKERS = (
    'GNU General Public License',
    'SPDX-License-Identifier',
    'Copyright (C)',
)

# Any HTML comment (non-greedy, across lines).
HTML_COMMENT_PATTERN = re.compile(r'<!--.*?-->', re.DOTALL)

def minify_css(css_content):
    """Minify CSS content"""
    # Remove comments
    css_content = re.sub(r'/\*.*?\*/', '', css_content, flags=re.DOTALL)
    
    # Remove newlines and extra whitespace
    css_content = re.sub(r'\s+', ' ', css_content)
    
    # Remove spaces around special characters
    css_content = re.sub(r'\s*([{}:;,>+~])\s*', r'\1', css_content)
    
    # Remove spaces after opening and before closing braces
    css_content = re.sub(r'{\s+', '{', css_content)
    css_content = re.sub(r'\s+}', '}', css_content)
    
    # Remove unnecessary semicolons before closing braces
    css_content = re.sub(r';}', '}', css_content)
    
    return css_content.strip()

def _regex_allowed(prev_char, last_word):
    """
    Decide whether a '/' at this point starts a regex literal (heuristic).
    A '/' starts a regex when the previous significant character is an operator,
    or the previous token is a keyword like return/typeof/case/...
    """
    if prev_char == '':
        return True
    if prev_char in _REGEX_PRECEDING_CHARS:
        return True
    if last_word in _REGEX_PRECEDING_KEYWORDS:
        return True
    return False

def _skip_quoted_string(js, i):
    """
    i points at the opening quote. Returns the index just past the closing quote,
    or the index of the line break if the string is unterminated on that line.
    """
    n = len(js)
    quote = js[i]
    i += 1
    while i < n:
        c = js[i]
        if c == '\\':
            i += 2
            continue
        if c == quote:
            return i + 1
        if c in '\r\n':
            return i
        i += 1
    return n

def _scan_regex_literal(js, i):
    """
    i points at the opening '/'. Returns the index just past the closing '/'
    and any flags, or -1 if this does not look like a regex literal.
    Character classes [...] and backslash escapes are skipped over.
    """
    n = len(js)
    j = i + 1
    in_class = False
    while j < n:
        c = js[j]
        if c == '\\':
            j += 2
            continue
        if c in '\r\n':
            return -1
        if in_class:
            if c == ']':
                in_class = False
            j += 1
            continue
        if c == '[':
            in_class = True
            j += 1
            continue
        if c == '/':
            j += 1
            while j < n and js[j].isalpha():
                j += 1
            return j
        j += 1
    return -1

def _skip_template_literal(js, i):
    """
    i points at the opening backtick. Returns the index just past the closing
    backtick. Handles escapes and ${ ... } interpolation (which may itself
    contain strings, nested templates and braces).
    """
    n = len(js)
    i += 1
    while i < n:
        c = js[i]
        if c == '\\':
            i += 2
            continue
        if c == '`':
            return i + 1
        if c == '$' and i + 1 < n and js[i + 1] == '{':
            i = _skip_template_expression(js, i + 2)
            continue
        i += 1
    return n

def _skip_template_expression(js, i):
    """
    i points just past '${'. Returns the index just past the matching '}'.
    Interpolations may contain strings, nested templates, regexes, comments
    and nested braces.
    """
    n = len(js)
    depth = 1
    prev_char = ''  # start of an interpolation behaves like start of input
    last_word = ''
    while i < n:
        c = js[i]
        if c == '\\':
            i += 2
            continue
        if c == '"' or c == "'":
            i = _skip_quoted_string(js, i)
            prev_char = c
            last_word = ''
            continue
        if c == '`':
            i = _skip_template_literal(js, i)
            prev_char = '`'
            last_word = ''
            continue
        if c == '/' and i + 1 < n and js[i + 1] == '/':
            i += 2
            while i < n and js[i] not in '\r\n':
                i += 1
            continue
        if c == '/' and i + 1 < n and js[i + 1] == '*':
            end = js.find('*/', i + 2)
            i = n if end == -1 else end + 2
            continue
        if c == '/' and _regex_allowed(prev_char, last_word):
            end = _scan_regex_literal(js, i)
            if end != -1:
                prev_char = '/'
                last_word = ''
                i = end
                continue
        if c == '{':
            depth += 1
            prev_char = c
            last_word = ''
            i += 1
            continue
        if c == '}':
            depth -= 1
            i += 1
            if depth == 0:
                return i
            prev_char = c
            last_word = ''
            continue
        if c.isalpha() or c == '_' or c == '$':
            start = i
            i += 1
            while i < n and (js[i].isalnum() or js[i] == '_' or js[i] == '$'):
                i += 1
            last_word = js[start:i]
            prev_char = last_word[-1]
            continue
        if not c.isspace():
            prev_char = c
            last_word = ''
        i += 1
    return n

def strip_js_comments(js):
    """
    Remove // line comments and /* ... */ block comments from JavaScript source
    with a character-scanning state machine (never a naive whole-content regex,
    so URLs like https:// inside strings are safe).

    - line comments: comment text removed, the following newline kept so ASI
      semantics are unchanged.
    - block comments: replaced with a single space.
    - string literals, template literals (including ${ ... } interpolation and
      nesting) and regex literals are skipped over untouched.
    - runs of 3+ newlines are collapsed to 2 (at most one blank line).

    The code itself is otherwise left intact (no whitespace mangling).
    """
    result = []
    i = 0
    n = len(js)
    prev_char = ''   # last significant (non-whitespace, non-comment) character
    last_word = ''   # last identifier/keyword token seen

    while i < n:
        ch = js[i]

        # // line comment: drop the text, keep the newline that follows
        if ch == '/' and i + 1 < n and js[i + 1] == '/':
            i += 2
            while i < n and js[i] not in '\r\n':
                i += 1
            continue

        # /* ... */ block comment: replace with a single space
        if ch == '/' and i + 1 < n and js[i + 1] == '*':
            end = js.find('*/', i + 2)
            i = n if end == -1 else end + 2
            result.append(' ')
            continue

        # string literals ("..." and '...'), backslash escapes respected
        if ch == '"' or ch == "'":
            end = _skip_quoted_string(js, i)
            result.append(js[i:end])
            prev_char = ch
            last_word = ''
            i = end
            continue

        # template literals (backticks), including ${ ... } interpolation
        if ch == '`':
            end = _skip_template_literal(js, i)
            result.append(js[i:end])
            prev_char = '`'
            last_word = ''
            i = end
            continue

        # regex literal vs division
        if ch == '/' and _regex_allowed(prev_char, last_word):
            end = _scan_regex_literal(js, i)
            if end != -1:
                result.append(js[i:end])
                prev_char = '/'
                last_word = ''
                i = end
                continue

        # identifiers and keywords
        if ch.isalpha() or ch == '_' or ch == '$':
            start = i
            i += 1
            while i < n and (js[i].isalnum() or js[i] == '_' or js[i] == '$'):
                i += 1
            word = js[start:i]
            result.append(word)
            prev_char = word[-1]
            last_word = word
            continue

        # ordinary characters
        result.append(ch)
        if not ch.isspace():
            prev_char = ch
            last_word = ''
        i += 1

    stripped = ''.join(result)
    # Collapse runs of 3+ newlines down to 2 (at most one blank line)
    stripped = re.sub(r'\n{3,}', '\n\n', stripped)
    # Trim trailing whitespace on each line (left where comments were removed).
    # Newlines are never removed, so automatic semicolon insertion is unaffected.
    stripped = '\n'.join(line.rstrip() for line in stripped.split('\n'))
    return stripped

def extract_preserved_comments(html_content):
    """
    Pull out the comments that must survive minification verbatim:
      (a) comment block(s) at the very start of the file (leading BOM/whitespace
          allowed), and
      (b) any comment containing "GNU General Public License",
          "SPDX-License-Identifier" or "Copyright (C)".

    Returns (preserved_text, spans). preserved_text keeps source order and each
    comment keeps its trailing newline if it had one; spans are (start, end)
    slices to cut out of the working content.
    """
    comments = list(HTML_COMMENT_PATTERN.finditer(html_content))
    if not comments:
        return '', []

    # Find comments sitting at the very beginning of the file.
    leading_ws = re.match(r'^[\ufeff\s]*', html_content)
    cursor = leading_ws.end() if leading_ws else 0
    leading_count = 0
    for comment in comments:
        if comment.start() == cursor:
            leading_count += 1
            cursor = comment.end()
            gap = re.match(r'[\ufeff\s]*', html_content[cursor:])
            cursor += gap.end() if gap else 0
        else:
            break

    preserved = []
    spans = []
    for index, comment in enumerate(comments):
        is_license = any(marker in comment.group(0)
                         for marker in LICENSE_COMMENT_MARKERS)
        if index >= leading_count and not is_license:
            continue
        start = 0 if index == 0 else comment.start()
        end = comment.end()
        # Preserve the trailing newline if it had one
        if html_content[end:end + 2] == '\r\n':
            end += 2
        elif end < len(html_content) and html_content[end] in '\r\n':
            end += 1
        spans.append((start, end))
        preserved.append(html_content[start:end])

    return ''.join(preserved), spans

def remove_comment_spans(html_content, spans):
    """Remove the given (start, end) spans from the content."""
    if not spans:
        return html_content
    pieces = []
    cursor = 0
    for start, end in sorted(spans):
        if start > cursor:
            pieces.append(html_content[cursor:start])
        cursor = max(cursor, end)
    pieces.append(html_content[cursor:])
    return ''.join(pieces)

def remove_html_comments(html_content):
    """Remove HTML comments but preserve IE conditional comments"""
    pattern = r'<!--(?!\[if.*?\]>|<!\[endif]).*?-->'
    return re.sub(pattern, '', html_content, flags=re.DOTALL)

def minify_html_content(html_content):
    """
    Minify HTML with special handling for style and script tags.
    Preserves the GPLv3 license comment verbatim at the top of the file,
    minifies CSS in style tags, and strips comments from the JS in script tags
    (the JS code itself is otherwise left intact).
    """
    # Extract (and temporarily remove) comments that must never be touched,
    # including the GPLv3 license header, BEFORE any comment removal runs.
    preserved_comments, preserved_spans = extract_preserved_comments(html_content)
    html_content = remove_comment_spans(html_content, preserved_spans)
    
    # Remove the remaining HTML comments
    html_content = remove_html_comments(html_content)
    
    # Pattern to match style, script, pre, and textarea tags
    pattern = r'(<style[^>]*>)(.*?)(</style>)|(<script[^>]*>)(.*?)(</script>)|(<pre[\s>].*?</pre>|<textarea[\s>].*?</textarea>)'
    
    def replacer(match):
        if match.group(1):  # <style> tag
            opening = match.group(1)
            css = match.group(2)
            closing = match.group(3)
            minified_css = minify_css(css)
            return f"{opening}{minified_css}{closing}"
        elif match.group(4):  # <script> tag
            # Keep the <script ...> and </script> tags themselves unchanged,
            # but strip comments out of the JavaScript body.
            opening = match.group(4)
            js = match.group(5)
            closing = match.group(6)
            return f"{opening}{strip_js_comments(js)}{closing}"
        else:  # <pre> or <textarea>
            return match.group(0)
    
    # Process all special tags
    processed = re.sub(pattern, replacer, html_content, flags=re.DOTALL | re.IGNORECASE)
    
    # Now minify the HTML outside of those tags
    # Split by the preserved tags
    preserve_pattern = r'(<style[^>]*>.*?</style>|<script[^>]*>.*?</script>|<pre[\s>].*?</pre>|<textarea[\s>].*?</textarea>)'
    segments = re.split(preserve_pattern, processed, flags=re.DOTALL | re.IGNORECASE)
    
    minified_segments = []
    for i, segment in enumerate(segments):
        # Check if this is a preserved tag
        if re.match(preserve_pattern, segment, flags=re.DOTALL | re.IGNORECASE):
            minified_segments.append(segment)
        else:
            # Minify HTML content
            # Remove newlines
            segment = re.sub(r'[\r\n]+', ' ', segment)
            # Compress multiple spaces to single space
            segment = re.sub(r'\s+', ' ', segment)
            # Remove spaces between tags
            segment = re.sub(r'>\s+<', '><', segment)
            # Remove spaces around = in attributes
            segment = re.sub(r'\s*=\s*', '=', segment)
            minified_segments.append(segment.strip())
    
    minified = ''.join(minified_segments)
    
    # Re-prepend the preserved license comment(s) verbatim at the very top
    if preserved_comments:
        return preserved_comments + minified.lstrip()
    
    return minified

def get_file_size_stats(original_content, minified_content, file_name):
    """Calculate file size statistics"""
    original_size = len(original_content.encode('utf-8'))
    minified_size = len(minified_content.encode('utf-8'))
    
    if original_size > 0:
        savings_percent = round((1 - minified_size / original_size) * 100, 1)
    else:
        savings_percent = 0
    
    return {
        'original_size': original_size,
        'minified_size': minified_size,
        'savings_percent': savings_percent,
        'file_name': file_name
    }

def process_html_file(file_path, no_minify=False):
    """Process a single HTML file and create a minified version"""
    try:
        # Read source file
        with open(file_path, 'r', encoding='utf-8') as f:
            original_content = f.read()
        
        # Process content
        if no_minify:
            processed_content = original_content
        else:
            processed_content = minify_html_content(original_content)
        
        # Create output filename
        path = Path(file_path)
        output_path = path.parent / f"{path.stem}.min{path.suffix}"
        
        # Get statistics
        stats = get_file_size_stats(original_content, processed_content, path.name)
        
        # Write minified file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(processed_content)
        
        # Display results
        print(f"\n  \033[36mProcessing: {path.name}\033[0m")
        
        if not no_minify:
            original_kb = round(stats['original_size'] / 1024, 1)
            minified_kb = round(stats['minified_size'] / 1024, 1)
            saved_kb = round((stats['original_size'] - stats['minified_size']) / 1024, 1)
            print(f"    \033[90mOriginal: {original_kb} KB\033[0m")
            print(f"    \033[32mMinified: {minified_kb} KB\033[0m")
            print(f"    \033[32mSaved: {stats['savings_percent']}% ({saved_kb} KB)\033[0m")
        else:
            original_kb = round(stats['original_size'] / 1024, 1)
            print(f"    \033[90mSize: {original_kb} KB (no minification)\033[0m")
        
        print(f"    \033[36mOutput: {output_path}\033[0m")
        
        return stats
        
    except Exception as e:
        print(f"\n  \033[31mError processing {file_path}: {str(e)}\033[0m")
        import traceback
        traceback.print_exc()
        return None

def process_directory(directory_path, no_minify=False):
    """Process all HTML files in a directory"""
    path = Path(directory_path)
    html_files = list(path.glob('*.html')) + list(path.glob('*.htm'))
    
    # Exclude already minified files
    html_files = [f for f in html_files if '.min.' not in f.name]
    
    if not html_files:
        print(f"\033[31mNo HTML files found in {directory_path}\033[0m")
        return
    
    print(f"\n\033[33mFound {len(html_files)} HTML file(s) to process\033[0m")
    
    # Track statistics
    total_original_size = 0
    total_minified_size = 0
    success_count = 0
    
    for html_file in html_files:
        stats = process_html_file(html_file, no_minify)
        if stats:
            total_original_size += stats['original_size']
            total_minified_size += stats['minified_size']
            success_count += 1
    
    # Calculate total savings
    if total_original_size > 0:
        total_savings = round((1 - total_minified_size / total_original_size) * 100, 1)
    else:
        total_savings = 0
    
    # Display overall statistics
    print("\n" + "=" * 64)
    print("\033[32mProcessing complete!\033[0m")
    print("=" * 64)
    
    original_kb = round(total_original_size / 1024, 1)
    minified_kb = round(total_minified_size / 1024, 1)
    saved_kb = round((total_original_size - total_minified_size) / 1024, 1)
    
    print("\n\033[33mOverall Statistics:\033[0m")
    print(f"  \033[36mFiles processed: {success_count}/{len(html_files)}\033[0m")
    print(f"  \033[90mOriginal total:  {original_kb} KB\033[0m")
    print(f"  \033[32mFinal total:     {minified_kb} KB\033[0m")
    
    if not no_minify:
        print(f"  \033[32mSpace saved:     {total_savings}% ({saved_kb} KB)\033[0m")
    
    method = "Full minification (HTML + CSS, preserves JS)" if not no_minify else "Copy without minification"
    print(f"  \033[90mMethod:          {method}\033[0m")

def main():
    parser = argparse.ArgumentParser(
        description='HTML/CSS/JS Minifier - Creates .min.html versions with full minification',
        epilog='Examples:\n'
               '  python3 minify_all.py index.html\n'
               '  python3 minify_all.py ./pages/\n'
               '  python3 minify_all.py index.html --no-minify',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('path', help='HTML file or directory to process')
    parser.add_argument('--no-minify', action='store_true', help='Skip minification (copy only)')
    args = parser.parse_args()
    
    target = args.path
    path = Path(target)
    
    if not path.exists():
        print(f"\033[31mError: '{target}' does not exist\033[0m")
        sys.exit(1)
    
    print("\033[33mHTML/CSS/JS Minifier\033[0m")
    print("Creates .min.html versions with full minification")
    
    if path.is_file():
        if path.suffix.lower() not in ['.html', '.htm']:
            print("\033[31mError: File must have .html or .htm extension\033[0m")
            sys.exit(1)
        
        stats = process_html_file(path, args.no_minify)
        
        if stats:
            print("\n" + "=" * 64)
            print("\033[32mProcessing complete!\033[0m")
            print("=" * 64)
            method = "Full minification (HTML + CSS, preserves JS)" if not args.no_minify else "Copy without minification"
            print(f"  \033[90mMethod: {method}\033[0m")
        
    elif path.is_dir():
        process_directory(path, args.no_minify)
    else:
        print(f"\033[31mError: '{target}' is neither a file nor a directory\033[0m")
        sys.exit(1)

if __name__ == "__main__":
    main()