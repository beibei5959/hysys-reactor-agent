"""Quick test for com_client.py fix on remote machine."""
import pythoncom
import win32com.client

pythoncom.CoInitialize()
app = win32com.client.GetActiveObject("HYSYS.Application")
case = app.ActiveDocument
fs = case.Flowsheet

# Test 1: attribute access (no parentheses)
print("=== Test 1: Attribute access ===")
streams = fs.MaterialStreams
print(f"MaterialStreams count: {streams.Count}")
for s in streams:
    print(f"  Stream: {s.Name}, T={s.Temperature()} K")

ops = fs.Operations
print(f"Operations count: {ops.Count}")
for op in ops:
    print(f"  Op: {op.TypeName}, Name={op.Name if hasattr(op, 'Name') else 'N/A'}")

# Test 2: import and test controller
print("\n=== Test 2: ComHysysController ===")
import sys
sys.path.insert(0, ".")
from src.hysys.com_client import ComHysysController

ctrl = ComHysysController()
ctrl.connect()
print(f"Connected: {ctrl.supports_simulation}")
print(f"Existing case: {ctrl._existing_case}")

# Test 3: find reactor
print("\n=== Test 3: Find reactor ===")
ops = fs.Operations
for op in ops:
    type_name = getattr(op, "TypeName", "")
    print(f"  Op type: {type_name}, name: {getattr(op, 'Name', 'N/A')}")

print("\nAll tests passed!")
pythoncom.CoUninitialize()
