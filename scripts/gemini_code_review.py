#!/usr/bin/env python3
"""
Code Review using Google Gemini API
Reviews all Python files in the repository and generates a detailed report
"""

import os
import json
import sys
from pathlib import Path
from typing import Optional
import google.generativeai as genai

# Configuration
GEMINI_MODEL = "gemini-2.0-flash"
EXCLUDE_DIRS = {'.git', '__pycache__', '.venv', 'venv', 'node_modules', '.pytest_cache', 'dist', 'build'}
EXCLUDE_FILES = {'*.pyc', '*.pyo', '.DS_Store'}
CODE_FILE_EXTENSIONS = {'.py', '.js', '.ts', '.java', '.cpp', '.go', '.rs', '.rb'}

class GeminiCodeReviewer:
    def __init__(self, api_key: Optional[str] = None):
        """Initialize Gemini code reviewer"""
        self.api_key = api_key or os.getenv('GEMINI_API_KEY')
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set")
        
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel(GEMINI_MODEL)
        self.review_results = []
        self.errors = []

    def get_code_files(self, root_dir: str = ".") -> list[str]:
        """Get all code files from repository"""
        code_files = []
        
        for root, dirs, files in os.walk(root_dir):
            # Remove excluded directories
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            
            # Skip certain paths
            if any(part in EXCLUDE_DIRS for part in root.split(os.sep)):
                continue
            
            for file in files:
                # Skip files in exclude list
                if any(file.endswith(pattern.replace('*', '')) for pattern in EXCLUDE_FILES):
                    continue
                
                # Check if file has code extension
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

    def review_code(self, file_path: str, content: str) -> dict:
        """Review a single code file using Gemini"""
        review_prompt = f"""
Please perform a thorough code review of the following file: {file_path}

Analyze the code for:
1. **Code Quality**: Check for readability, maintainability, and adherence to best practices
2. **Performance**: Identify potential performance issues
3. **Security**: Look for security vulnerabilities or unsafe patterns
4. **Testing**: Comment on test coverage and testability
5. **Documentation**: Check for proper documentation and comments
6. **Error Handling**: Verify proper error handling
7. **Design Patterns**: Suggest improvements using design patterns

Code:
```
{content}
```

Provide your review in JSON format with these sections:
{{
  "file": "{file_path}",
  "severity": "critical|warning|info",
  "issues": [
    {{
      "line": <line_number>,
      "severity": "critical|warning|info",
      "category": "<category>",
      "issue": "<description>",
      "suggestion": "<recommended fix>"
    }}
  ],
  "summary": "<overall assessment>",
  "strengths": ["<positive aspect>"],
  "improvements": ["<improvement suggestion>"],
  "score": <0-100>
}}

IMPORTANT: Return ONLY valid JSON, no additional text.
"""
        
        try:
            response = self.model.generate_content(review_prompt)
            response_text = response.text.strip()
            
            # Clean up markdown code blocks if present
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            if response_text.startswith('```'):
                response_text = response_text[3:]
            if response_text.endswith('```'):
                response_text = response_text[:-3]
            
            response_text = response_text.strip()
            return json.loads(response_text)
            
        except json.JSONDecodeError as e:
            self.errors.append(f"JSON parsing error for {file_path}: {str(e)}")
            return {
                "file": file_path,
                "severity": "error",
                "summary": f"Error parsing review response: {str(e)}",
                "issues": [],
                "score": 0
            }
        except Exception as e:
            self.errors.append(f"Error reviewing {file_path}: {str(e)}")
            return {
                "file": file_path,
                "severity": "error",
                "summary": f"Error: {str(e)}",
                "issues": [],
                "score": 0
            }

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
            
            # Skip very large files (> 10KB)
            if len(content) > 10000:
                print(f"  ⊘ Skipped (file too large: {len(content)} bytes)")
                continue
            
            review = self.review_code(file_path, content)
            self.review_results.append(review)
            
            if review.get("score"):
                print(f"  Score: {review['score']}/100")
        
        return self.review_results

    def generate_report(self, output_file: str = "code-review-report.md") -> str:
        """Generate markdown report from review results"""
        report = ["# 📋 Code Review Report\n"]
        
        # Summary
        total_files = len(self.review_results)
        critical_issues = sum(
            len(r.get("issues", [])) 
            for r in self.review_results 
            if r.get("severity") == "critical"
        )
        avg_score = sum(r.get("score", 0) for r in self.review_results) / max(total_files, 1) if total_files > 0 else 0
        
        report.append("## Summary\n")
        report.append(f"- **Files Reviewed**: {total_files}")
        report.append(f"- **Critical Issues**: {critical_issues}")
        report.append(f"- **Average Score**: {avg_score:.1f}/100\n")
        
        if self.errors:
            report.append("## Errors\n")
            for error in self.errors:
                report.append(f"- ⚠️  {error}\n")
        
        # Detailed reviews
        report.append("## Detailed Reviews\n")
        
        for review in self.review_results:
            file_path = review.get("file", "Unknown")
            score = review.get("score", 0)
            summary = review.get("summary", "No summary")
            
            report.append(f"### {file_path}")
            report.append(f"**Score**: {score}/100\n")
            report.append(f"**Summary**: {summary}\n")
            
            # Issues
            issues = review.get("issues", [])
            if issues:
                report.append("**Issues Found**:\n")
                for issue in issues:
                    severity = issue.get("severity", "info").upper()
                    category = issue.get("category", "General")
                    problem = issue.get("issue", "Unknown issue")
                    suggestion = issue.get("suggestion", "N/A")
                    
                    report.append(f"- [{severity}] **{category}**: {problem}")
                    report.append(f"  → Suggestion: {suggestion}\n")
            
            # Strengths
            strengths = review.get("strengths", [])
            if strengths:
                report.append("**Strengths**:\n")
                for strength in strengths:
                    report.append(f"- ✓ {strength}\n")
            
            # Improvements
            improvements = review.get("improvements", [])
            if improvements:
                report.append("**Recommended Improvements**:\n")
                for improvement in improvements:
                    report.append(f"- 💡 {improvement}\n")
            
            report.append("\n---\n")
        
        # Write report
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(report))
        
        return output_file

def main():
    """Main function"""
    try:
        print("🤖 Initializing Gemini Code Reviewer...\n")
        reviewer = GeminiCodeReviewer()
        
        # Review repository
        reviewer.review_repository()
        
        # Generate report
        report_file = reviewer.generate_report()
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