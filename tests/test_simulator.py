from simulator.esp_simulator import signal

def test_normal():
    x = signal("ESP-101", 1, "normal")
    assert x["status"] == "RUNNING"
    assert x["flow_rate"] > 0

def test_low_flow():
    x = signal("ESP-101", 1, "low_flow")
    assert x["flow_rate"] < 60
    assert x["motor_temperature"] > 120

def test_shutdown():
    x = signal("ESP-101", 1, "shutdown")
    assert x["status"] == "SHUTDOWN"
    assert x["flow_rate"] == 0
