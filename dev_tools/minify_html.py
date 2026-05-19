#!/usr/bin/env python3
"""
HTML Minifier
Creates .min.html versions of HTML files without modifying originals
Usage: python3 minify_html.py <file.html|directory>
"""

import os
import sys
import argparse
import re
from pathlib import Path
from datetime import datetime

def remove_html_comments(html_content):
    """Remove HTML comments but preserve IE conditional comments"""
    # This regex matches <!-- --> but not <!--[if ...]> or <![endif]-->
    pattern = r'<!--(?!\[if.*?\]>|<!\[endif]).*?-->'
    html_content = re.sub(pattern, '', html_content, flags=re.DOTALL)
    return html_content

def lightly_minify_html(html_content):
    """Light minification: only remove comments and newlines, preserve script/style/pre tags"""
    # Remove HTML comments (except IE conditionals)
    html_content = remove_html_comments(html_content)
    
    # Split content to preserve script, style, pre, and textarea tags
    preserve_tags = r'(<script[\s>].*?</script>|<style[\s>].*?</style>|<pre[\s>].*?</pre>|<textarea[\s>].*?</textarea>)'
    segments = re.split(preserve_tags, html_content, flags=re.DOTALL | re.IGNORECASE)
    
    minified_segments = []
    for segment in segments:
        # Check if this segment is a preserved tag
        if re.match(preserve_tags, segment, flags=re.DOTALL | re.IGNORECASE):
            # Keep the tag content as-is
            minified_segments.append(segment)
        else:
            # Minify other content
            segment = re.sub(r'[\r\n]+', ' ', segment)
            segment = re.sub(r'\s+', ' ', segment)
            segment = segment.strip()
            minified_segments.append(segment)
    
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
            processed_content = lightly_minify_html(original_content)
        
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
    
    method = "Light minification (comments/newlines only, preserves scripts)" if not no_minify else "Copy without minification"
    print(f"  \033[90mMethod:          {method}\033[0m")

def main():
    parser = argparse.ArgumentParser(
        description='HTML Minifier - Creates .min.html versions without modifying originals',
        epilog='Examples:\n'
               '  python3 minify_html.py index.html\n'
               '  python3 minify_html.py ./games/\n'
               '  python3 minify_html.py index.html --no-minify',
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
    
    print("\033[33mHTML Minifier\033[0m")
    print("Creates .min.html versions without modifying originals")
    
    if path.is_file():
        if path.suffix.lower() not in ['.html', '.htm']:
            print("\033[31mError: File must have .html or .htm extension\033[0m")
            sys.exit(1)
        
        stats = process_html_file(path, args.no_minify)
        
        if stats:
            print("\n" + "=" * 64)
            print("\033[32mProcessing complete!\033[0m")
            print("=" * 64)
            method = "Light minification (comments/newlines only, preserves scripts)" if not args.no_minify else "Copy without minification"
            print(f"  \033[90mMethod: {method}\033[0m")
        
    elif path.is_directory():
        process_directory(path, args.no_minify)
    else:
        print(f"\033[31mError: '{target}' is neither a file nor a directory\033[0m")
        sys.exit(1)

if __name__ == "__main__":
    main()
