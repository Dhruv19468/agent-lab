"""Step 0 check: can we reach our Azure OpenAI deployment?

Run from the backend/ folder:
    uv run --env-file .env --with openai python scripts/check_azure_openai.py
"""

from __future__ import annotations

import os
import sys

from openai import APIConnectionError, AuthenticationError, NotFoundError, OpenAI


def read_setting(name: str) -> str:
    """Read one required environment variable, or stop with a clear message."""
    value = os.getenv(name, "").strip()
    if not value:
        sys.exit(f"Missing {name}. Is it set in backend/.env?")
    return value


def main() -> None:
    endpoint = read_setting("AZURE_OPENAI_ENDPOINT")
    api_key = read_setting("AZURE_OPENAI_API_KEY")
    deployment = read_setting("AZURE_OPENAI_DEPLOYMENT")

    # The v1 API speaks the standard OpenAI protocol, so the normal OpenAI client works:
    # we only point it at our Azure URL instead of api.openai.com.
    client = OpenAI(api_key=api_key, base_url=endpoint)

    print(f"Calling deployment '{deployment}' at {endpoint} ...")

    try:
        response = client.chat.completions.create(
            model=deployment,  # on Azure this is the DEPLOYMENT name
            messages=[
                {"role": "system", "content": "You are a helpful assistant. Answer in one sentence."},
                {"role": "user", "content": "What is a test plan in software testing?"},
            ],
            max_completion_tokens=100,
        )
    except AuthenticationError:
        sys.exit("401: the API key was rejected. Copy KEY 1 again into AZURE_OPENAI_API_KEY.")
    except NotFoundError:
        sys.exit(
            "404: endpoint or deployment not found. Check that the endpoint ends with "
            "/openai/v1/ and that AZURE_OPENAI_DEPLOYMENT is the deployment name."
        )
    except APIConnectionError:
        sys.exit("Could not connect. Check the endpoint URL and your internet/VPN.")

    answer = response.choices[0].message.content
    usage = response.usage

    print("\nModel answer:")
    print(answer)
    print(f"\nModel used : {response.model}")
    print(f"Tokens     : {usage.prompt_tokens} in + {usage.completion_tokens} out "
          f"= {usage.total_tokens} total")


if __name__ == "__main__":
    main()