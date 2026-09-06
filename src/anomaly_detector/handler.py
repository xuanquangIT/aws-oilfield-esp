import os, json, base64, boto3
sns = boto3.client("sns")
topic = os.environ["ALERT_TOPIC_ARN"]

def classify(x):
    if x.get("status") == "SHUTDOWN":
        return "shutdown", "critical"
    flow = float(x.get("flow_rate", 0))
    temp = float(x.get("motor_temperature", 0))
    vib = float(x.get("vibration", 0))
    current = float(x.get("motor_current", 0))
    tubing = float(x.get("tubing_pressure", 0))
    reasons = []
    if flow < 60 and temp > 120: reasons.append("low flow + motor overheating")
    if vib > 12 and current > 75: reasons.append("high vibration + elevated current")
    if tubing > 900 and flow < 60: reasons.append("high tubing pressure + low flow")
    if x.get("scenario") == "gas_slug": reasons.append("gas-slug simulation")
    if not reasons: return "normal", "normal"
    return "; ".join(reasons), ("critical" if len(reasons) >= 2 else "warning")

def handler(event, context):
    alerts = 0
    for record in event.get("Records", []):
        item = json.loads(base64.b64decode(record["kinesis"]["data"]).decode())
        finding, severity = classify(item)
        if severity != "normal":
            sns.publish(
                TopicArn=topic,
                Subject=f"ESP {item['esp_id']} {severity.upper()}",
                Message=json.dumps({"esp_id": item["esp_id"], "timestamp": item["timestamp"],
                                     "severity": severity, "finding": finding, "signals": item}, indent=2),
            )
            alerts += 1
    return {"alerts": alerts}
