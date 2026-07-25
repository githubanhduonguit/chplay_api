#!/usr/bin/env python3
"""
Pull Request Code Review using Cerebras API
Hỗ trợ Inline Comment theo dòng trên Bitbucket
"""

import os
import json
import subprocess
from typing import Optional
from openai import OpenAI
import requests

CEREBRAS_MODEL = "gpt-oss-120b"

CODE_EXTENSIONS = (
    ".py", ".js", ".ts", ".tsx", ".jsx",
    ".java", ".go", ".rs", ".kt", ".swift",
    ".cpp", ".c", ".h", ".cs"
)


class CerebrasPRReviewer:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("CEREBRAS_API_KEY")
        if not self.api_key:
            raise ValueError("CEREBRAS_API_KEY environment variable not set")

        self.client = OpenAI(
            base_url="https://api.cerebras.ai/v1",
            api_key=self.api_key
        )
        self.model = CEREBRAS_MODEL

    def _get_base_branch(self) -> str:
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
        """Lấy danh sách file thay đổi + diff của từng file"""
        try:
            base_branch = self._get_base_branch()
            print(f"📌 Base branch: origin/{base_branch}")

            subprocess.run(
                ["git", "fetch", "origin", base_branch, "--depth=1"],
                capture_output=True,
                text=True,
            )

            # Lấy danh sách file thay đổi
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

                if status.startswith("D") or not file_path.endswith(CODE_EXTENSIONS):
                    continue

                # Lấy unified diff của file
                diff_result = subprocess.run(
                    ["git", "diff", f"origin/{base_branch}...HEAD", "--", file_path],
                    capture_output=True,
                    text=True,
                )

                # Lấy nội dung file mới (để model có context đầy đủ nếu cần)
                content_result = subprocess.run(
                    ["git", "show", f"HEAD:{file_path}"],
                    capture_output=True,
                    text=True,
                )

                if diff_result.returncode == 0:
                    changed_files.append({
                        "path": file_path,
                        "status": status,
                        "diff": diff_result.stdout,
                        "content": content_result.stdout if content_result.returncode == 0 else "",
                    })

            return changed_files
        except Exception as e:
            print(f"❌ Error getting changed files: {e}")
            return []

    def review_pr_file(self, file_path: str, diff: str, content: str = "") -> dict:
        """Review file dựa trên diff, yêu cầu trả về số dòng"""
        prompt = f"""
Bạn là senior software engineer đang review Pull Request.

File: {file_path}

Đây là diff (chỉ những dòng thay đổi):
```diff
{diff}