"""Dashboard Overview Page helper."""
from typing import Any, Dict
from dashboard.app import build_dashboard_state
from database.models import ExecutionEnvironment


def get_overview_section(env: ExecutionEnvironment = ExecutionEnvironment.PAPER) -> Dict[str, Any]:
    return build_dashboard_state(env)["overview"]
