from tool.tools import Tool
from datetime import datetime

class TimenowTool(Tool):
    def __init__(self):
        super().__init__("get_current_time", "Get the current time", {
            "type": "object",
            "properties": {},
            "required": []
        })

    def handler(self, manager, **kwargs) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
