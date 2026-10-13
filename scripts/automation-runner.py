#!/usr/bin/env python3
"""Run the same automation worker implementation used by the Docker service."""

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCAL_SERVICE_SOURCE = PROJECT_ROOT / "apps" / "local-service" / "src"
sys.path.insert(0, str(LOCAL_SERVICE_SOURCE))

from job_search_assistant.automation.runner import main  # noqa: E402


if __name__ == "__main__":
    main()
