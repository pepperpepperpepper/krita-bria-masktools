#!/usr/bin/env python3
"""Simple linting script for Krita plugin"""

import ast
import sys
import re

def check_syntax(filename):
    """Check Python syntax"""
    try:
        with open(filename, 'r') as f:
            ast.parse(f.read())
        return True, "Syntax OK"
    except SyntaxError as e:
        return False, f"Syntax Error at line {e.lineno}: {e.msg}"

def check_common_issues(filename):
    """Check for common issues"""
    issues = []
    
    with open(filename, 'r') as f:
        lines = f.readlines()
    
    for i, line in enumerate(lines, 1):
        # Check for tabs
        if '\t' in line:
            issues.append(f"Line {i}: Contains tabs (use spaces)")
        
        # Check for trailing whitespace
        if line.rstrip() != line.rstrip('\n').rstrip('\r'):
            issues.append(f"Line {i}: Trailing whitespace")
        
        # Check for long lines
        if len(line.rstrip()) > 120:
            issues.append(f"Line {i}: Line too long ({len(line.rstrip())} > 120)")
        
        # Check for print statements left in code
        if re.match(r'^\s*print\s*\(', line):
            issues.append(f"Line {i}: Contains print statement (consider removing)")
    
    return issues

def main():
    filename = 'krita_bria_masktools/krita_bria_masktools.py'
    
    print(f"Linting {filename}...")
    
    # Check syntax
    syntax_ok, msg = check_syntax(filename)
    if not syntax_ok:
        print(f"❌ {msg}")
        sys.exit(1)
    else:
        print(f"✓ {msg}")
    
    # Check common issues
    issues = check_common_issues(filename)
    if issues:
        print("\nIssues found:")
        for issue in issues:
            print(f"  ⚠️  {issue}")
    else:
        print("✓ No common issues found")
    
    print("\n✅ Linting complete")

if __name__ == "__main__":
    main()