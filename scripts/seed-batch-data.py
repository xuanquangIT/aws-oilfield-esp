import csv, random
from datetime import datetime, timedelta, timezone
from pathlib import Path
out=Path("data/historical.csv")
start=datetime.now(timezone.utc)-timedelta(days=7)
rows=[]
for i in range(7*24):
    ts=start+timedelta(hours=i)
    for esp in ["ESP-101","ESP-102","ESP-103"]:
        flow=110+random.uniform(-10,10)
        rows.append([ts.isoformat(),esp,round(flow,2),.35,700,1600,92,68,2.5,"RUNNING"])
with out.open("w",newline="") as f:
    w=csv.writer(f); w.writerow(["timestamp","esp_id","flow_rate","water_cut","intake_pressure","discharge_pressure","motor_temperature","motor_current","vibration","status"]); w.writerows(rows)
print(out)
