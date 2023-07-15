from build.api_signature_tool import pySignatureTool
import base64
import json

tool = pySignatureTool({})

salt = "salt"
salt = base64.b64encode(salt.encode("utf-8")).decode("utf-8")

with open("../keys/private_request.txt") as f:
    private_key = f.read()

with open("../signature") as f:
    signature = f.read()

result = tool.process({
    "payload": {
        "call": "generate",
        "private-key": base64.b64encode(private_key.encode("utf-8")).decode("utf-8"),
        "signature": base64.b64encode(signature.encode("utf-8")).decode("utf-8"),
    },
    "salt": salt
})
print("generate response", result)

with open("../license", 'w') as f:
    f.write(result['certificate'])

with open("../license") as f:
    certificate = f.read()

with open("../keys/public_request.txt") as f:
    public_key = f.read()

result = tool.process({
    "payload": {
        "call": "verify",
        "public-key": base64.b64encode(public_key.encode("utf-8")).decode("utf-8"),
        "certificate": certificate,
        "signature": base64.b64encode(signature.encode("utf-8")).decode("utf-8")
    },
    "salt": salt
})
print("verify response", result)

result = tool.process({
    "payload": {
        "call": "FeatureInfo",
        "feature": "DatabaseLimit",
        "version": "",
        "field": "numLicenses",
        "server": "192.168.45.61"
    },
    "salt": salt
})
print(json.loads(result['original']))
