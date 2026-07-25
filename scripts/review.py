import os
import sys
import requests

# ==========================
# Configuration
# ==========================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
BITBUCKET_TOKEN = os.getenv("BITBUCKET_STEP_OAUTH_TOKEN")

WORKSPACE = os.getenv("BITBUCKET_WORKSPACE")
REPO = os.getenv("BITBUCKET_REPO_SLUG")
PR_ID = os.getenv("BITBUCKET_PR_ID")

GEMINI_MODEL = "gemini-2.5-pro"

# ==========================
# Validate environment
# ==========================
required = {
    "GEMINI_API_KEY": GEMINI_API_KEY,
    "BITBUCKET_STEP_OAUTH_TOKEN": BITBUCKET_TOKEN,
    "BITBUCKET_WORKSPACE": WORKSPACE,
    "BITBUCKET_REPO_SLUG": REPO,
    "BITBUCKET_PR_ID": PR_ID,
}

missing = [k for k, v in required.items() if not v]

if missing:
    print("Missing environment variables:")
    for item in missing:
        print(f" - {item}")
    sys.exit(1)

headers = {
    "Authorization": f"Bearer {BITBUCKET_TOKEN}"
}


# ==========================
# Get PR Diff
# ==========================
def get_pr_diff():
    url = (
        f"https://api.bitbucket.org/2.0/"
        f"repositories/{WORKSPACE}/{REPO}"
        f"/pullrequests/{PR_ID}/diff"
    )

    r = requests.get(url, headers=headers)

    if r.status_code != 200:
        raise Exception(
            f"Cannot get diff\nStatus={r.status_code}\n{r.text}"
        )

    return r.text


# ==========================
# Call Gemini
# ==========================
def review_with_gemini(diff):

    prompt = f"""
You are a Senior Software Engineer.

Review ONLY the code changes below.

Focus on:

1. Bugs
2. Security issues
3. Performance problems
4. Clean code
5. Best practices

Do NOT comment on formatting only.

Reply in Markdown.

Code diff:

{diff}
"""

    url = (
        "https://generativelanguage.googleapis.com/"
        f"v1beta/models/{GEMINI_MODEL}:generateContent"
        f"?key={GEMINI_API_KEY}"
    )

    body = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt
                    }
                ]
            }
        ]
    }

    r = requests.post(url, json=body)

    if r.status_code != 200:
        raise Exception(
            f"Gemini Error\nStatus={r.status_code}\n{r.text}"
        )

    data = r.json()

    return data["candidates"][0]["content"]["parts"][0]["text"]


# ==========================
# Comment PR
# ==========================
def post_comment(comment):

    url = (
        f"https://api.bitbucket.org/2.0/"
        f"repositories/{WORKSPACE}/{REPO}"
        f"/pullrequests/{PR_ID}/comments"
    )

    body = {
        "content": {
            "raw": f"## 🤖 Gemini Code Review\n\n{comment}"
        }
    }

    r = requests.post(
        url,
        headers={
            **headers,
            "Content-Type": "application/json",
        },
        json=body,
    )

    if r.status_code not in (200, 201):
        raise Exception(
            f"Cannot post comment\nStatus={r.status_code}\n{r.text}"
        )


# ==========================
# Main
# ==========================
def main():

    print("Downloading PR diff...")

    diff = get_pr_diff()

    if len(diff.strip()) == 0:
        print("No changes found.")
        return

    print(f"Diff size: {len(diff)} chars")

    # tránh vượt token
    MAX_DIFF = 30000

    if len(diff) > MAX_DIFF:
        print("Diff too large. Truncating...")
        diff = diff[:MAX_DIFF]

    print("Calling Gemini...")

    review = review_with_gemini(diff)

    print(review)

    print("Posting comment...")

    post_comment(review)

    print("Done.")


if __name__ == "__main__":
    main()