#!/usr/bin/env python3
"""
Code Review using Cerebras API
Reviews all code files and generates inline comments
"""

import os
import json
import sys
from pathlib import Path
from typing import Optional
import requests

# Configuration
CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY")
CEREBRAS_MODEL = "llama-3.1-70b"
CEREBRAS_BASE_URL = "https://api.cerebras.ai/v1"

EXCLUDE_DIRS = {
    '.git', '__pycache__', '.venv', 'venv', 'node_modules', '.pytest_cache', 
    'dist', 'build', '.next', 'out', 'coverage', '.tox'
}
EXCLUDE_FILES = {'*.pyc', '*.pyo', '.DS_Store'}
CODE_FILE_EXTENSIONS = {'.py', '.js', '.ts', '.tsx', '.jsx', '.java', '.cpp', '.go', '.rs', '.rb', '.kt', '.swift'}


class CerebrasCodeReviewer:
    def __init__(self, api_key: Optional[str] = None):
        """Initialize Cerebras code reviewer"""
        self.api_key = api_key or os.getenv("CEREBRAS_API_KEY")
        if not self.api_key:
            raise ValueError("CEREBRAS_API_KEY environment variable not set")

        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        self.review_results = []
        self.errors = []

    def get_code_files(self, root_dir: str = ".") -> list[str]:
        """Get all code files from repository"""
        code_files = []

        for root, dirs, files in os.walk(root_dir):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]

            if any(part in EXCLUDE_DIRS for part in root.split(os.sep)):
                continue

            for file in files:
                if any(file.endswith(pattern.replace('*', '')) for pattern in EXCLUDE_FILES):
                    continue

                file_ext = Path(file).suffix
                if file_ext in CODE_FILE_EXTENSIONS:
                    file_path = os.path.join(root, file)
                    code_files.append(file_path)

        return sorted(code_files)

    def read_file_content(self, file_path: str) -> Optional[str]:
        """Read file content safely"""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        except Exception as e:
            self.errors.append(f"Error reading {file_path}: {str(e)}")
            return None

    def review_code_inline(self, file_path: str, content: str) -> dict:
        """Review code file line-by-line"""
        lines = content.split('\n')
        file_review = {
            "file": file_path,
            "total_lines": len(lines),
            "inline_comments": [],
            "score": 100,
            "summary": "No issues found"
        }

        print(f"  🔍 Analyzing {len(lines)} lines...")

        # Review toàn bộ file để lấy overview
        overview_review = self._get_overview_review(file_path, content)

        if overview_review.get("has_issues"):
            # Nếu có issues, review từng dòng
            for line_num, line_content in enumerate(lines, 1):
                if line_num % 50 == 0:
                    print(f"    Line {line_num}/{len(lines)}...")
                
                if line_content.strip():  # Skip empty lines
                    line_review = self._review_line_detailed(file_path, line_num, line_content)
                    if line_review.get("comments"):
                        file_review["inline_comments"].append(line_review)

            file_review["score"] = max(0, 100 - len(file_review["inline_comments"]) * 5)
            file_review["summary"] = f"Found {len(file_review['inline_comments'])} issue(s)"
        else:
            file_review["summary"] = overview_review.get("summary", "Well-written code")
            file_review["score"] = 95

        return file_review

    def _get_overview_review(self, file_path: str, content: str) -> dict:
        """Get overview review để xác định có issues không"""
        prompt = f"""Quickly review this file {file_path} and identify if there are any code issues.

File size: {len(content)} bytes
Lines: {len(content.split(chr(10)))}

Sample of code:
{content[:1000]}

Respond in JSON:
{{
  "has_issues": true|false,
  "summary": "<brief assessment>",
  "issue_types": ["<type1>", "<type2>"]
}}

Return ONLY valid JSON."""

        try:
            response = requests.post(
                f"{CEREBRAS_BASE_URL}/chat/completions",
                headers=self.headers,
                json={
                    "model": CEREBRAS_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "max_tokens": 300,
                },
                timeout=15,
            )

            if response.status_code == 200:
                response_data = response.json()
                response_text = response_data["choices"][0]["message"]["content"].strip()

                if response_text.startswith("```json"):
                    response_text = response_text[7:]
                if response_text.startswith("```"):
                    response_text = response_text[3:]
                if response_text.endswith("```"):
                    response_text = response_text[:-3]

                return json.loads(response_text.strip())
            return {"has_issues": False, "summary": "Unable to review"}
        except:
            return {"has_issues": False, "summary": "Review unavailable"}

    def _review_line_detailed(self, file_path: str, line_num: int, line_content: str) -> dict:
        """Review một dòng code chi tiết"""
        prompt = f"""Review this single line from {file_path} at line {line_num}:

Line {line_num}: {line_content}

Identify specific issues if any. Respond in JSON:
{{
  "line": {line_num},
  "file": "{file_path}",
  "comments": [
    {{
      "severity": "critical|warning|info",
      "issue": "<specific issue>",
      "suggestion": "<how to fix>"
    }}
  ]
}}

If no issues, return {{"line": {line_num}, "comments": []}}
Return ONLY valid JSON."""

        try:
            response = requests.post(
                f"{CEREBRAS_BASE_URL}/chat/completions",
                headers=self.headers,
                json={
                    "model": CEREBRAS_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2,
                    "max_tokens": 200,
                },
                timeout=10,
            )

            if response.status_code == 200:
                response_data = response.json()
                response_text = response_data["choices"][0]["message"]["content"].strip()

                if response_text.startswith("```json"):
                    response_text = response_text[7:]
                if response_text.startswith("```"):
                    response_text = response_text[3:]
                if response_text.endswith("```"):
                    response_text = response_text[:-3]

                result = json.loads(response_text.strip())
                if result.get("comments"):
                    return result
            return {"line": line_num, "comments": []}
        except:
            return {"line": line_num, "comments": []}

    def review_repository(self, root_dir: str = ".") -> list[dict]:
        """Review all code files in repository"""
        print("🔍 Scanning repository for code files...")
        code_files = self.get_code_files(root_dir)

        if not code_files:
            print("⚠️  No code files found to review")
            return []

        print(f"📂 Found {len(code_files)} code files to review\n")

        for idx, file_path in enumerate(code_files, 1):
            print(f"[{idx}/{len(code_files)}] Reviewing: {file_path}")

            content = self.read_file_content(file_path)
            if not content:
                continue

            if len(content) > 50000:
                print(f"  ⊘ Skipped (file too large: {len(content)} bytes)")
                continue

            review = self.review_code_inline(file_path, content)
            self.review_results.append(review)

            issues_count = len(review["inline_comments"])
            print(f"  Score: {review['score']}/100 | Issues: {issues_count}")

        return self.review_results

    def generate_inline_comment_report(self, output_file: str = "code-review-inline.md") -> str:
        """Generate report with inline comments"""
        report = ["# 📋 Code Review Report - Inline Comments\n"]

        total_files = len(self.review_results)
        total_issues = sum(len(r.get("inline_comments", [])) for r in self.review_results)
        avg_score = sum(r.get("score", 0) for r in self.review_results) / max(total_files, 1) if total_files > 0 else 0

        report.append("## Summary\n")
        report.append(f"- **Files Reviewed**: {total_files}")
        report.append(f"- **Total Issues**: {total_issues}")
        report.append(f"- **Average Score**: {avg_score:.1f}/100\n")

        report.append("## Issues by File\n")

        for file_review in self.review_results:
            file_path = file_review.get("file", "Unknown")
            score = file_review.get("score", 0)
            summary = file_review.get("summary", "")
            inline_comments = file_review.get("inline_comments", [])

            report.append(f"### `{file_path}`\n")
            report.append(f"**Score**: {score}/100 | **Issues**: {len(inline_comments)}\n")

            if inline_comments:
                report.append("**Inline Comments**:\n")
                for comment in inline_comments:
                    line_num = comment.get("line", "?")
                    report.append(f"\n#### Line {line_num}\n")
                    
                    for issue in comment.get("comments", []):
                        severity = issue.get("severity", "info").upper()
                        problem = issue.get("issue", "")
                        suggestion = issue.get("suggestion", "")
                        
                        icon = "🔴" if severity == "CRITICAL" else "🟡" if severity == "WARNING" else "ℹ️"
                        report.append(f"{icon} **[{severity}]** {problem}\n")
                        if suggestion:
                            report.append(f"   💡 Suggestion: {suggestion}\n")
            else:
                report.append("✓ No issues found\n")

            report.append("\n---\n")

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(report))

        return output_file


def main():
    """Main function"""
    try:
        print("🤖 Initializing Cerebras Code Reviewer...\n")
        reviewer = CerebrasCodeReviewer()

        reviewer.review_repository()

        report_file = reviewer.generate_inline_comment_report()
        print(f"\n✅ Code review report generated: {report_file}")

        return 0
    except KeyboardInterrupt:
        print("\n⚠️  Review interrupted by user")
        return 130
    except Exception as e:
        print(f"\n❌ Error: {str(e)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())