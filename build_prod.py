"""
Build script for production deployment.
Run before pushing to Railway to minify frontend code.

Usage: python build_prod.py
"""
import os
import re
from pathlib import Path


def minify_html(content: str) -> str:
    """Remove HTML comments and excessive whitespace."""
    # Remove HTML comments (but keep IE conditionals)
    content = re.sub(r'<!--(?!\[if).*?-->', '', content, flags=re.DOTALL)
    # Remove excessive blank lines (keep max 1)
    content = re.sub(r'\n\s*\n\s*\n', '\n\n', content)
    return content


def minify_js_basic(content: str) -> str:
    """Basic JS minification — remove comments only (not whitespace to keep debuggable)."""
    # Remove single-line comments (but not URLs with //)
    content = re.sub(r'(?<!:)//(?!/)[^\n]*', '', content)
    # Remove multi-line comments
    content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
    return content


def main():
    static_dir = Path(__file__).parent / "static"
    
    html_files = list(static_dir.glob("*.html"))
    js_files = list((static_dir / "js").glob("*.js")) if (static_dir / "js").exists() else []
    
    print(f"Minifying {len(html_files)} HTML files and {len(js_files)} JS files...")
    
    total_saved = 0
    for f in html_files:
        original = f.read_text(encoding='utf-8')
        minified = minify_html(original)
        saved = len(original) - len(minified)
        if saved > 0:
            f.write_text(minified, encoding='utf-8')
            total_saved += saved
            print(f"  {f.name}: -{saved} bytes")
    
    for f in js_files:
        original = f.read_text(encoding='utf-8')
        minified = minify_js_basic(original)
        saved = len(original) - len(minified)
        if saved > 0:
            f.write_text(minified, encoding='utf-8')
            total_saved += saved
            print(f"  {f.name}: -{saved} bytes")
    
    print(f"\nTotal saved: {total_saved} bytes ({total_saved/1024:.1f} KB)")
    print("Done. Ready for Railway deployment.")


if __name__ == "__main__":
    main()
