#!/usr/bin/env python3
"""
Pull Request Code Review using Google Gemini API
Reviews changed files in pull requests and posts comments
"""

import os
import json
import subprocess
from typing import Optional
import google.generativeai as genai

GEMINI_MODEL = "gemini-2.0-flash"

class GeminiPRReviewer:
    def __init__(self, api_key: Optional[str] = None):
        """Initialize PR reviewer"""
        self.api_key = api_key or os.getenv('GEMINI_API_KEY')
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set")
        
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel(GEMINI_MODEL)

    def get_changed_files(self) -> list[dict]:
        """Get changed files from git diff"""
        try:
            # Get diff from merge-base (for PR context)
            result = subprocess.run(
                ["git", "diff", "--name-status", "origin/develop...HEAD"],
                capture_output=True,
                text=True
            )
            
            changed_files = []
            for line in result.stdout.strip().split('\n'):
                if not line:
                    continue
                
                parts = line.split('\t')
                status = parts[0]
                file_path = parts[1]
                
                # Skip deleted files and non-code files
                if status == 'D' or not file_path.endswith(('.py', '.js', '.ts', '.java')):
                    continue
                
                # Get file content
                content_result = subprocess.run(
                    ["git", "show", f"HEAD:{file_path}"],
                    capture_output=True,
                    text=True
                )
                
                if content_result.returncode == 0:
                    changed_files.append({
                        'path': file_path,
                        'status': status,
                        'content': content_result.stdout
                    })
            
            return changed_files
        except Exception as e:
            print(f"Error getting changed files: {e}")
            return []

    def review_pr_file(self, file_path: str, content: str) -> dict:
        """Review a file changed in PR"""
        prompt = f"""
Review this code file from a pull request: {file_path}

Focus on:
1. Logic correctness and potential bugs
2. Performance issues
3. Security vulnerabilities
4. Code style and consistency
5. Breaking changes

Code:
```
{content}
```

Provide feedback as JSON:
{{
  "file": "{file_path}",
  "approved": true|false,
  "comments": [
    {{
      "severity": "critical|warning|info",
      "message": "<concise feedback>",
      "line_suggestion": "<code suggestion if applicable>"
    }}
  ],
  "summary": "<overall feedback>",
  "require_changes": true|false
}}

Return ONLY valid JSON.
"""
        
        try:
            response = self.model.generate_content(prompt)
            response_text = response.text.strip()
            
            # Clean markdown
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            if response_text.startswith('```'):
                response_text = response_text[3:]
            if response_text.endswith('```'):
                response_text = response_text[:-3]
            
            return json.loads(response_text.strip())
        except json.JSONDecodeError:
            return {
                "file": file_path,
                "approved": False,
                "comments": [{
                    "severity": "warning",
                    "message": "Could not parse review response"
                }],
                "summary": "Review encountered an error",
                "require_changes": False
            }

    def review_pull_request(self) -> dict:
        """Review all files in pull request"""
        print("📋 Reviewing pull request...\n")
        
        changed_files = self.get_changed_files()
        if not changed_files:
            print("ℹ️  No code files changed in this PR")
            return {"approved": True, "files": []}
        
        print(f"🔍 Found {len(changed_files)} changed file(s)\n")
        
        pr_review = {
            "files": [],
            "approved": True,
            "require_changes": False,
            "total_issues": 0
        }
        
        for file_info in changed_files:
            file_path = file_info['path']
            content = file_info['content']
            
            print(f"Reviewing: {file_path}")
            review = self.review_pr_file(file_path, content)
            
            pr_review["files"].append(review)
            
            if not review.get("approved"):
                pr_review["approved"] = False
            
            if review.get("require_changes"):
                pr_review["require_changes"] = True
            
            num_comments = len(review.get("comments", []))
            pr_review["total_issues"] += num_comments
            
            if num_comments > 0:
                print(f"  ⚠️  {num_comments} issue(s) found")
            else:
                print(f"  ✓ No issues found")
        
        return pr_review

    def post_review_comment(self, review: dict):
        """Post review as PR comment (Bitbucket API)"""
        pr_id = os.getenv('BITBUCKET_PR_ID')
        repo_url = os.getenv('BITBUCKET_REPO_FULL_NAME')
        username = os.getenv('BITBUCKET_USERNAME')
        password = os.getenv('BITBUCKET_PASSWORD')
        
        if not all([pr_id, repo_url, username, password]):
            print("⚠️  Bitbucket credentials not available, skipping comment")
            return
        
        # Build comment
        comment = self._build_comment(review)
        
        try:
            import requests
            url = f"https://api.bitbucket.org/2.0/repositories/{repo_url}/pullrequests/{pr_id}/comments"
            
            response = requests.post(
                url,
                json={"content": {"raw": comment}},
                auth=(username, password)
            )
            
            if response.status_code == 201:
                print("✓ Review comment posted to PR")
            else:
                print(f"⚠️  Failed to post comment: {response.status_code}")
        except Exception as e:
            print(f"⚠️  Error posting comment: {e}")

    def _build_comment(self, review: dict) -> str:
        """Build markdown comment from review"""
        lines = ["## 🤖 AI Code Review (Gemini)\n"]
        
        if review["approved"]:
            lines.append("✅ **Approved** - No blocking issues found\n")
        else:
            lines.append("❌ **Changes Required** - Please address the issues below\n")
        
        lines.append(f"**Summary**: {review['total_issues']} issue(s) found\n")
        
        if review["require_changes"]:
            lines.append("**Status**: ⏸️ Changes required before merge\n")
        
        lines.append("\n### Issues by File\n")
        
        for file_review in review["files"]:
            file_path = file_review.get("file", "Unknown")
            summary = file_review.get("summary", "")
            comments = file_review.get("comments", [])
            
            lines.append(f"#### {file_path}")
            if summary:
                lines.append(f"{summary}\n")
            
            if comments:
                for comment in comments:
                    severity = comment.get("severity", "info")
                    message = comment.get("message", "")
                    lines.append(f"- **[{severity.upper()}]** {message}")
            else:
                lines.append("- ✓ No issues\n")
        
        return '\n'.join(lines)

def main():
    """Main function"""
    try:
        reviewer = GeminiPRReviewer()
        review = reviewer.review_pull_request()
        
        # Save review JSON
        with open("pr-review.json", "w") as f:
            json.dump(review, f, indent=2)
        
        # Post comment
        reviewer.post_review_comment(review)
        
        # Exit with appropriate code
        return 0 if review["approved"] else 1
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1

if __name__ == "__main__":
    import sys
    sys.exit(main())