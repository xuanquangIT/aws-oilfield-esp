import argparse, json, math, random, time
from datetime import datetime, timezone
import boto3

def signal(esp, tick, scenario):
    flow, intake, discharge = 120+random.uniform(-4,4), 700+random.uniform(-8,8), 1600+random.uniform(-15,15)
    temp, vib, current = 92+random.uniform(-2,2), 2.5+random.uniform(-.3,.3), 68+random.uniform(-2,2)
    tubing, casing, freq = 700+random.uniform(-10,10), 500+random.uniform(-10,10), 60.0
    status = "RUNNING"
    if scenario == "gas_slug":
        wave = math.sin(tick/5)*35; flow += wave; intake -= wave*.6; current += abs(wave)*.15
    elif scenario == "low_flow":
        flow, temp, current, discharge = 42+random.uniform(-3,3), 137+random.uniform(-3,3), 82+random.uniform(-2,2), 1510
    elif scenario == "mechanical":
        vib = min(16, 3+tick*.08)+random.uniform(-.5,.5); current = 72+tick*.06; discharge -= min(220,tick*1.5)
    elif scenario == "blockage":
        tubing, flow, discharge, current, temp = 1000+random.uniform(-20,20), 42+random.uniform(-3,3), 1630, 84, 125
    elif scenario == "sensor_fault":
        temp = 91.0
    elif scenario == "shutdown":
        status, flow, current, freq, vib, temp = "SHUTDOWN", 0.0, 0.0, 0.0, 0.0, 75.0
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(), "esp_id": esp, "scenario": scenario, "status": status,
        "intake_pressure": round(intake,2), "discharge_pressure": round(discharge,2),
        "intake_temperature": 78.0, "motor_temperature": round(temp,2),
        "vibration": round(max(vib,0),2), "motor_current": round(max(current,0),2),
        "pump_frequency": freq, "tubing_pressure": round(tubing,2), "casing_pressure": round(casing,2),
        "flow_rate": round(max(flow,0),2), "water_cut": .35,
    }

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--stream-name", required=True)
    p.add_argument("--scenario", default="normal", choices=["normal","gas_slug","low_flow","mechanical","blockage","sensor_fault","shutdown"])
    p.add_argument("--seconds", type=int, default=600)
    p.add_argument("--interval", type=float, default=1)
    a = p.parse_args()
    k = boto3.client("kinesis")
    for tick in range(a.seconds):
        for esp in ["ESP-101","ESP-102","ESP-103"]:
            x = signal(esp, tick, a.scenario)
            k.put_record(StreamName=a.stream_name, Data=(json.dumps(x)+"\n").encode(), PartitionKey=esp)
        time.sleep(a.interval)

if __name__ == "__main__":
    main()
