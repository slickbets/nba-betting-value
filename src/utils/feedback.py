"""Submit user feedback as Linear issues."""

import os
import requests

LINEAR_API_URL = "https://api.linear.app/graphql"
LINEAR_TEAM_ID = "6d369a5d-677b-417e-99ab-1451d967a214"

# Label IDs from Linear
LABEL_MAP = {
    "Bug": "78798ea5-8714-4a4c-bb98-4de4275fb9f8",
    "Feature Request": "c82b7294-5d96-4384-8869-03e8c9b90997",
    "General Feedback": "ed7eb238-c3e6-4e95-bf49-077cdd756fb5",
}


def submit_feedback(title: str, description: str, category: str = "Improvement") -> bool:
    """Create a Linear issue from user feedback. Returns True on success."""
    api_key = os.getenv("LINEAR_API_KEY", "")
    if not api_key:
        return False

    label_id = LABEL_MAP.get(category)
    label_input = f', labelIds: ["{label_id}"]' if label_id else ""

    mutation = """
    mutation {
      issueCreate(input: {
        title: "%s"
        description: "%s"
        teamId: "%s"
        %s
      }) {
        success
      }
    }
    """ % (
        title.replace('"', '\\"'),
        description.replace('"', '\\"').replace("\n", "\\n"),
        LINEAR_TEAM_ID,
        label_input,
    )

    try:
        r = requests.post(
            LINEAR_API_URL,
            json={"query": mutation},
            headers={"Authorization": api_key},
            timeout=10,
        )
        data = r.json()
        return data.get("data", {}).get("issueCreate", {}).get("success", False)
    except Exception:
        return False
