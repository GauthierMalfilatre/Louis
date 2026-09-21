from tool.tools import Tool

class TimenowTool(Tool):
    def __init__(self, name, description, parameters):
        super().__init__("get_current_time", "Get the current time", {
            "type": "object",
            "properties": {},
            "required": []
        })

    def handler(self, manager):
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
