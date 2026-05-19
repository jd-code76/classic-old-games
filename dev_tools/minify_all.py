#!/usr/bin/env python3
"""
HTML/CSS/JS Minifier
Creates .min.html versions with minified CSS and preserved JavaScript
Usage: python3 minify_all.py <file.html|directory>
"""

import os
import sys
import argparse
import re
from pathlib import Path

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

def remove_html_comments(html_content):
    """Remove HTML comments but preserve IE conditional comments"""
    pattern = r'<!--(?!\[if.*?\]>|<!\[endif]).*?-->'
    return re.sub(pattern, '', html_content, flags=re.DOTALL)

def minify_html_content(html_content):
    """
    Minify HTML with special handling for style and script tags.
    Preserves JavaScript in script tags, minifies CSS in style tags.
    """
    # Remove HTML comments first
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
            # Keep script tags completely intact
            return match.group(0)
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
    
    return ''.join(minified_segments)

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
        
    elif path.is_directory():
        process_directory(path, args.no_minify)
    else:
        print(f"\033[31mError: '{target}' is neither a file nor a directory\033[0m")
        sys.exit(1)

if __name__ == "__main__":
    main()
