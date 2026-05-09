import json
class Tool:
    def __init__(self):
        self.parameters = {}
        self.name = "test"
        self.description = "test"

tool = Tool()
prompt = f"""Parameters: {json.dumps(tool.parameters.get('properties', {{}}), indent=2)}"""
print(prompt)
