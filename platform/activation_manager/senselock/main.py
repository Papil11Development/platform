from build.api_senselock import pyHardwareKey

usr_pin = [0xe4, 0xda, 0x0b, 0x71, 0xb9, 0x53, 0x46, 0x7c]

config = {"usr_pin": usr_pin}
key = pyHardwareKey(config)

print(key.process({"call": "readStaticData"}))

print(key.process({"call": "readStateData"}))

key.process({"call": "writeStateData", "data": "test"})

print(key.process({"call": "readStateData"}))
