from tool.tool import Tool
from ddgs import DDGS
import json

class InternetTool(Tool):
    def __init__(self):
        super().__init__("web_search", "Recherche sur internet des informations récentes ou que tu ne connais pas.", {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "La requête de recherche"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Nombre de résultats (défaut 5)"
                }
            },
            "required": ["query"]
        })

    def handle(self, manager, **kwargs) -> str:
        query = kwargs.get("query")
        max_results = kwargs.get("max_results")
        results = DDGS().text(query, max_results=max_results)
        res = json.dumps(
            [
                {
                    "title": r["title"],
                    "url": r["href"],
                    "snippet": r["body"]
                }
                for r in results
            ],
            ensure_ascii=False
        )
        return res
