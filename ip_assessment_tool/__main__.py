"""Entry point for running the IP Assessment Tool as a module.

Usage: python -m ip_assessment_tool [options]
"""

import sys

from ip_assessment_tool.cli import main

sys.exit(main())
