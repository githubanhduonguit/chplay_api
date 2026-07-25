#!/usr/bin/env python3
"""
Pull Request Code Review using Cerebras API
Reviews changed files in pull requests and posts inline comments per line
"""

import os
import json
import subprocess
from typing import Optional
import requests

CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY")
CEREBRAS_MODEL = "poolside/laguna-s-2.1:free"
CEREBRAS_BASE_URL = "https://openrouter.ai/api/v1"

# Các extension được review
CODE_EXTENSIONS = (
    ".py", ".js", ".ts", ".tsx", ".jsx",
    ".java", ".go", ".rs", ".kt", ".swift",
    ".cpp", ".c", ".h", ".cs"
)


class CerebrasPRReviewer:
    def __init__(self, api_key: Optional[str] = None):
        """Initialize PR reviewer with Cerebras API"""
        self.api_key = api_key or os.getenv("CEREBRAS_API_KEY")
        if not self.api_key:
            raise ValueError("CEREBRAS_API_KEY environment variable not set")
        
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def _get_base_branch(self) -> str:
        """Xác định base branch của PR"""
        dest = os.getenv("BITBUCKET_PR_DESTINATION_BRANCH")
        if dest:
            return dest

        for branch in ("main", "master", "develop"):
            result = subprocess.run(
                ["git", "rev-parse", "--verify", f"origin/{branch}"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return branch

        return "main"

    def get_changed_files(self) -> list[dict]:
        """Get changed files from git diff"""
        try:
            base_branch = self._get_base_branch()
            print(f"📌 Base branch: origin/{base_branch}")

            subprocess.run(
                ["git", "fetch", "origin", base_branch, "--depth=1"],
                capture_output=True,
                text=True,
            )

            # Lấy danh sách files thay đổi
            result = subprocess.run(
                ["git", "diff", "--name-status", f"origin/{base_branch}...HEAD"],
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                print(f"⚠️  git diff failed: {result.stderr.strip()}")
                return []

            changed_files = []
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue

                parts = line.split("\t")
                if len(parts) < 2:
                    continue

                status = parts[0]
                file_path = parts[-1]

                # Bỏ qua file xóa và file không phải code
                if status.startswith("D") or not file_path.endswith(CODE_EXTENSIONS):
                    continue

                # Lấy nội dung file ở HEAD
                content_result = subprocess.run(
                    ["git", "show", f"HEAD:{file_path}"],
                    capture_output=True,
                    text=True,
                )

                if content_result.returncode == 0:
                    # Lấy line numbers của các dòng thay đổi
                    diff_result = subprocess.run(
                        ["git", "diff", f"origin/{base_branch}...HEAD", "--", file_path],
                        capture_output=True,
                        text=True,
                    )
                    
                    changed_lines = self._parse_changed_lines(diff_result.stdout)
                    
                    changed_files.append({
                        "path": file_path,
                        "status": status,
                        "content": content_result.stdout,
                        "changed_lines": changed_lines,
                    })

            return changed_files
        except Exception as e:
            print(f"❌ Error getting changed files: {e}")
            return []

    def _parse_changed_lines(self, diff_output: str) -> list[int]:
        """Parse git diff output để lấy line numbers của dòng thay đổi"""
        changed_lines = []
        lines = diff_output.split('\n')
        current_line = 0
        
        for line in lines:
            # Hunk header format: @@ -start,count +start,count @@
            if line.startswith('@@'):
                # Extract the line number from the new file
                parts = line.split(' ')
                if len(parts) >= 3:
                    new_hunk = parts[2]  # e.g., "+10,20"
                    if new_hunk.startswith('+'):
                        start_line = int(new_hunk.split(',')[0][1:])
                        current_line = start_line
            elif line.startswith('+') and not line.startswith('+++'):
                # Added line
                changed_lines.append(current_line)
                current_line += 1
            elif line.startswith('-') and not line.startswith('---'):
                # Deleted line - không cần track
                pass
            elif not line.startswith('\\'):
                # Normal line
                if line.startswith(' ') or len(line) == 0:
                    current_line += 1
        
        return changed_lines

    def review_pr_file(self, file_path: str, content: str, changed_lines: list[int]) -> dict:
        """Review a file changed in PR sử dụng Cerebras API"""
        lines = content.split('\n')
        reviewed_lines = {}
        
        print(f"  📝 Reviewing {len(changed_lines)} changed lines...")
        
        for idx, line_num in enumerate(changed_lines, 1):
            if line_num > 0 and line_num <= len(lines):
                line_content = lines[line_num - 1].strip()
                
                # Skip empty lines và comments
                if not line_content or line_content.startswith('#') or line_content.startswith('//'):
                    continue
                
                # Show progress
                if idx % 10 == 0:
                    print(f"    Progress: {idx}/{len(changed_lines)}...")
                
                review = self._review_line(file_path, line_num, line_content)
                
                # Chỉ lưu nếu có issues
                if review.get("comments"):
                    reviewed_lines[line_num] = review
        
        total_issues = sum(len(r.get("comments", [])) for r in reviewed_lines.values())
        
        return {
            "file": file_path,
            "reviewed_lines": reviewed_lines,
            "total_issues": total_issues,
            "approved": total_issues == 0,
        }

    def _review_line(self, file_path: str, line_num: int, line_content: str) -> dict:
        """Review một dòng code chi tiết"""
        prompt = f"""CRITICAL: Review this code line CAREFULLY and identify ALL specific issues:

File: {file_path}
Line {line_num}: {line_content}

You MUST check for:
1. Security vulnerabilities (SQL injection, XSS, command injection, etc)
2. Performance issues (N+1, inefficient loops, memory leaks)
3. Logic errors (off-by-one, type mismatches, null checks)
4. Best practices violations (naming, error handling, validation)
5. Code smells (dead code, magic numbers, complexity)

If you find ANY issue, describe it SPECIFICALLY with exact problem and fix.
If NO issues, say "No issues".

Format as JSON:
{{
  "line": {line_num},
  "file": "{file_path}",
  "has_issues": true/false,
  "comments": [
    {{
      "severity": "critical|warning|info",
      "category": "<exact category>",
      "issue": "<SPECIFIC problem found>",
      "suggestion": "<exact fix>"
    }}
  ]
}}

Be SPECIFIC. Examples:
- BAD: "Variable naming issue"
- GOOD: "Variable 'x' should be 'user_id' for clarity"
- BAD: "Security problem"
- GOOD: "SQL injection: string concatenation in query() - use parameterized query"
"""

        try:
            response = requests.post(
                f"{CEREBRAS_BASE_URL}/chat/completions",
                headers=self.headers,
                json={
                    "model": CEREBRAS_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,  # Lower = stricter
                    "max_tokens": 500,   # More tokens for detail
                },
                timeout=15,
            )

            if response.status_code != 200:
                print(f"    ⚠️ API error: {response.status_code}")
                return {"line": line_num, "comments": [], "has_issues": False}

            response_data = response.json()
            response_text = response_data["choices"][0]["message"]["content"].strip()

            # Clean markdown
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]

            result = json.loads(response_text.strip())
            
            # Verify we got actual issues
            if result.get("comments"):
                print(f"    Line {line_num}: Found {len(result['comments'])} issue(s)")
            
            return result
        except json.JSONDecodeError as e:
            print(f"    ⚠️ JSON parse error on line {line_num}: {e}")
            return {"line": line_num, "comments": [], "has_issues": False}
        except Exception as e:
            print(f"    ⚠️ Error: {e}")
            return {"line": line_num, "comments": [], "has_issues": False}

    def review_pull_request(self) -> dict:
        """Review all files in pull request"""
        print("📋 Reviewing pull request...\n")

        changed_files = self.get_changed_files()
        if not changed_files:
            print("ℹ️  No code files changed in this PR")
            return {
                "approved": True, 
                "files": [], 
                "total_issues": 0, 
                "inline_comments": []
            }

        print(f"🔍 Found {len(changed_files)} changed file(s)\n")

        pr_review = {
            "files": [],
            "approved": True,
            "total_issues": 0,
            "inline_comments": [],
        }

        for file_info in changed_files:
            file_path = file_info["path"]
            content = file_info["content"]
            changed_lines = file_info["changed_lines"]

            print(f"Reviewing: {file_path} ({len(changed_lines)} changed lines)")
            review = self.review_pr_file(file_path, content, changed_lines)

            pr_review["files"].append(review)
            pr_review["total_issues"] += review.get("total_issues", 0)

            # Tạo inline comments
            for line_num, line_review in review.get("reviewed_lines", {}).items():
                for comment in line_review.get("comments", []):
                    inline_comment = {
                        "file": file_path,
                        "line": int(line_num),
                        "severity": comment.get("severity", "info"),
                        "message": comment.get("message", ""),
                    }
                    pr_review["inline_comments"].append(inline_comment)
                    print(f"  ⚠️  Line {line_num}: {comment.get('message', '')}")

            if review.get("total_issues", 0) == 0:
                print(f"  ✓ No issues found")

        if pr_review["total_issues"] == 0:
            pr_review["approved"] = True

        return pr_review

    def post_inline_comments(self, review: dict):
        """Post inline comments trên Bitbucket PR"""
        pr_id = os.getenv("BITBUCKET_PR_ID")
        repo_full_name = os.getenv("BITBUCKET_REPO_FULL_NAME")
        username = os.getenv("BITBUCKET_USERNAME")
        api_token = os.getenv("BITBUCKET_API_TOKEN") or os.getenv("BITBUCKET_PASSWORD")

        if not all([pr_id, repo_full_name, username, api_token]):
            print("⚠️  Missing Bitbucket credentials → skip inline comments")
            print("   Set: BITBUCKET_USERNAME, BITBUCKET_API_TOKEN in Repository variables")
            return

        inline_comments = review.get("inline_comments", [])
        if not inline_comments:
            print("✓ No issues found - no comments to post")
            return

        print(f"\n📝 Posting {len(inline_comments)} detailed inline comment(s)...\n")

        for idx, comment in enumerate(inline_comments, 1):
            file_path = comment["file"]
            line_num = comment["line"]
            message = comment["message"]
            severity = comment["severity"]

            print(f"  [{idx}/{len(inline_comments)}] {file_path}:{line_num}")
            self._post_single_comment(
                pr_id, repo_full_name, username, api_token,
                file_path, line_num, message, severity
            )

    def _post_single_comment(self, pr_id: str, repo_full_name: str, username: str, 
                            api_token: str, file_path: str, line_num: int, 
                            message: str, severity: str):
        """Post một inline comment trên Bitbucket"""
        try:
            # Bitbucket API endpoint để post inline comment
            url = f"https://api.bitbucket.org/2.0/repositories/{repo_full_name}/pullrequests/{pr_id}/comments"

            # Format message với severity
            icon = "🔴" if severity == "critical" else "🟡" if severity == "warning" else "ℹ️"
            formatted_message = f"{icon} **[{severity.upper()}]** {message}\n\n*By Cerebras AI Code Review*"

            # Tạo payload cho inline comment
            payload = {
                "content": {
                    "raw": formatted_message
                },
                "inline": {
                    "to": line_num,
                    "path": file_path
                }
            }

            response = requests.post(
                url,
                json=payload,
                auth=(username, api_token),
                timeout=30,
            )

            if response.status_code == 201:
                print(f"  ✓ Comment posted on {file_path}:{line_num}")
            else:
                print(f"  ⚠️  Failed to post on {file_path}:{line_num} - Status {response.status_code}")
        except Exception as e:
            print(f"  ⚠️  Error posting comment: {e}")

    def post_summary_comment(self, review: dict):
        """Post tóm tắt review dưới dạng PR comment"""
        pr_id = os.getenv("BITBUCKET_PR_ID")
        repo_full_name = os.getenv("BITBUCKET_REPO_FULL_NAME")
        username = os.getenv("BITBUCKET_USERNAME")
        api_token = os.getenv("BITBUCKET_API_TOKEN") or os.getenv("BITBUCKET_PASSWORD")

        if not all([pr_id, repo_full_name, username, api_token]):
            return

        comment = self._build_summary_comment(review)

        try:
            url = f"https://api.bitbucket.org/2.0/repositories/{repo_full_name}/pullrequests/{pr_id}/comments"

            response = requests.post(
                url,
                json={"content": {"raw": comment}},
                auth=(username, api_token),
                timeout=30,
            )

            if response.status_code == 201:
                print("✓ Summary comment posted to PR")
            else:
                print(f"⚠️  Failed to post summary: {response.status_code}")
        except Exception as e:
            print(f"⚠️  Error posting summary: {e}")

    def _build_summary_comment(self, review: dict) -> str:
        """Build tóm tắt comment"""
        total_issues = review.get("total_issues", 0)
        approved = review.get("approved", True)

        lines = ["## 🤖 Cerebras Code Review Summary\n"]

        if approved:
            lines.append("✅ **APPROVED** - No issues found!\n")
        else:
            lines.append(f"❌ **REVIEW REQUIRED** - {total_issues} issue(s) found\n")

        lines.append(f"\n**Files Reviewed**: {len(review.get('files', []))}\n")
        lines.append(f"**Issues Found**: {total_issues}\n")
        lines.append("\n*Inline comments posted on affected lines*\n")

        return "\n".join(lines)


def main():
    """Main function"""
    try:
        reviewer = CerebrasPRReviewer()
        review = reviewer.review_pull_request()

        # Save review JSON
        with open("pr-review.json", "w", encoding="utf-8") as f:
            json.dump(review, f, indent=2, ensure_ascii=False)

        # Post inline comments
        reviewer.post_inline_comments(review)

        # Post summary
        reviewer.post_summary_comment(review)

        print("\n✅ Code review completed!")
        return 0 if review.get("approved", True) else 1
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())