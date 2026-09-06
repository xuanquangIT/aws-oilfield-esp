import os, json, base64, boto3
from datetime import datetime, timezone

s3 = boto3.client("s3")
table = boto3.resource("dynamodb").Table(os.environ["STATE_TABLE"])
bucket = os.environ["DATA_BUCKET"]

def handler(event, context):
    count = 0
    for record in event.get("Records", []):
        item = json.loads(base64.b64decode(record["kinesis"]["data"]).decode())
        ts = item.get("timestamp") or datetime.now(timezone.utc).isoformat()
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        esp = item["esp_id"]
        key = f"raw/realtime/{esp}/{dt:%Y/%m/%d/%H}/{record['kinesis']['sequenceNumber']}.json"
        s3.put_object(Bucket=bucket, Key=key, Body=(json.dumps(item)+"\n").encode(), ContentType="application/json")
        table.put_item(Item={
            "esp_id": esp,
            "timestamp": ts,
            "status": item.get("status", "UNKNOWN"),
            "flow_rate": str(item.get("flow_rate", "")),
            "motor_temperature": str(item.get("motor_temperature", "")),
            "motor_current": str(item.get("motor_current", "")),
            "vibration": str(item.get("vibration", "")),
            "scenario": item.get("scenario", "unknown"),
        })
        count += 1
    return {"processed": count}
