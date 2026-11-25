"""Pre-execution code safety scanner for AI-generated code.

Scans Python source for dangerous patterns BEFORE the Executor runs it.
Returns a list of violations. If non-empty, the code is rejected and
sent back to the Coder with a SAFETY_VIOLATION correction trigger.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import Any


@dataclass
class Violation:
    line: int
    pattern: str
    severity: str  # "critical" | "warning"
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "line": self.line,
            "pattern": self.pattern,
            "severity": self.severity,
            "description": self.description,
        }


# Regex-based patterns (fast pre-filter)
_DANGEROUS_PATTERNS: list[tuple[str, str, str]] = [
    (r"\bos\.system\s*\(", "os.system()", "Arbitrary shell command execution"),
    (r"\bsubprocess\.(call|run|Popen)\s*\(", "subprocess.*", "Shell subprocess execution"),
    (r"\bshutil\.rmtree\s*\(", "shutil.rmtree()", "Recursive directory deletion"),
    (r"\bos\.remove\s*\(", "os.remove()", "File deletion"),
    (r"\bos\.rmdir\s*\(", "os.rmdir()", "Directory deletion"),
    (r"\b__import__\s*\(", "__import__()", "Dynamic import bypass"),
    (r"\bopen\s*\(.*/etc/", "open(/etc/...)", "Sensitive system file access"),
]

# AST-based: dangerous imports
_BANNED_IMPORTS: set[str] = {
    "ctypes", "socket", "http.server", "xmlrpc",
    "multiprocessing", "signal",
}


def scan(source: str) -> list[Violation]:
    """Scan Python source code for safety violations.
    
    Returns an empty list if the code is safe.
    """
    violations: list[Violation] = []

    # --- 1. Regex scan (catches string-level patterns) ---
    for lineno, line in enumerate(source.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        for pattern, name, desc in _DANGEROUS_PATTERNS:
            if re.search(pattern, line):
                violations.append(Violation(
                    line=lineno,
                    pattern=name,
                    severity="critical",
                    description=desc,
                ))

    # --- 2. AST scan (catches structural patterns) ---
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return violations  # syntax errors are the Executor's problem

    for node in ast.walk(tree):
        # Banned imports
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in _BANNED_IMPORTS:
                    violations.append(Violation(
                        line=node.lineno,
                        pattern=f"import {alias.name}",
                        severity="critical",
                        description=f"Banned module: {root}",
                    ))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root = node.module.split(".")[0]
                if root in _BANNED_IMPORTS:
                    violations.append(Violation(
                        line=node.lineno,
                        pattern=f"from {node.module} import ...",
                        severity="critical",
                        description=f"Banned module: {root}",
                    ))

        # eval() / exec() on non-literal input
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in ("eval", "exec"):
                # Allow eval/exec of string literals (common in test harnesses)
                if node.args and isinstance(node.args[0], ast.Constant):
                    continue
                violations.append(Violation(
                    line=node.lineno,
                    pattern=f"{func.id}()",
                    severity="critical",
                    description=f"Dynamic {func.id}() on non-literal input",
                ))

    return violations
