import aws_cdk as cdk
from infrastructure.core_stack import CoreStack
from infrastructure.dashboard_hosted_stack import DashboardHostedStack
from infrastructure.realtime_stack import RealtimeStack

app = cdk.App()
prefix = app.node.try_get_context("project_prefix") or "oilfield-esp"

core = CoreStack(app, f"{prefix}-core", project_prefix=prefix)
RealtimeStack(app, f"{prefix}-realtime", project_prefix=prefix, core=core)
DashboardHostedStack(app, f"{prefix}-dashboard-hosted", project_prefix=prefix, core=core)

app.synth()
