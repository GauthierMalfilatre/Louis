##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Tests of the tool calls (T1): the model asks for a tool in the middle of its answer, Louis runs it, gives it the
## result, and the model goes on with it. The model is a script of replies: no Ollama
##
from events.event_list import TOOL_CALL_STARTED, TOOL_CALL_ENDED, CHAT_TURN_ENDED
from model.reply import Reply
from tool.tool import Tool, failed
from tool.tool_call import ToolCall
from tool.tool_manager import ToolManager

class Add(Tool):
    """ A calculator: what it was called with is kept """
    def __init__(self):
        super().__init__("add", "Additionne a et b.", {
            "type": "object", "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}}, "required": ["a", "b"]})
        self.calls: list[dict] = []

    def handle(self, app, **kwargs) -> str:
        self.calls.append(kwargs)
        return str(kwargs["a"] + kwargs["b"])

class Crashing(Tool):
    def __init__(self):
        super().__init__("crash", "Plante.", {"type": "object", "properties": {}})

    def handle(self, app, **kwargs) -> str:
        raise RuntimeError("disque plein")

def tool_results(app) -> list[str]:
    return [message["content"] for message in app.session.history if message["role"] == "tool"]

def test_a_call_comes_and_goes_in_the_format_of_the_api():
    call = ToolCall.from_dict({"function": {"name": "add", "arguments": {"a": 1, "b": 2}}})
    assert call == ToolCall("add", {"a": 1, "b": 2})
    assert ToolCall.from_dict(call.to_dict()) == call
    assert ToolCall.from_dict({"function": {"name": "tree"}}).arguments == {}

def test_the_manager_offers_the_schema_of_each_tool():
    add = Add()
    manager = ToolManager().register(add)
    assert manager.has("add") and manager.get("add") is add
    [schema] = manager.all()
    assert schema["type"] == "function" and schema["function"]["name"] == "add"
    assert schema["function"]["parameters"]["required"] == ["a", "b"]
    assert not manager.unregister("add").has("add") and manager.get("add") is None

def test_louis_offers_its_own_tools_to_the_model(chat):
    app = chat([Reply(content="Bonjour.")])
    app._App__answer("Salut")
    assert {"tree", "cat_file", "search", "write_file", "edit_file", "mkdir", "web_search", "git"} <= set(app.sent[0]["tools"])

def test_the_model_calls_a_tool_reads_its_result_and_answers_with_it(chat):
    add = Add()
    app = chat([Reply(tool_calls=[ToolCall("add", {"a": 17, "b": 25})]), Reply(content="17 + 25 = 42.")])
    app._App__toolManager.register(add)
    app._App__answer("Combien font 17 + 25 ?")
    assert add.calls == [{"a": 17, "b": 25}]
    # The second request reads the call and its result, then the model answers
    second = app.sent[1]["messages"]
    assert second[-2]["tool_calls"] == [{"function": {"name": "add", "arguments": {"a": 17, "b": 25}}}]
    assert (second[-1]["role"], second[-1]["content"]) == ("tool", "42")
    assert app.session.history[-1] == {"role": "assistant", "content": "17 + 25 = 42."}
    [started], [ended] = app.listener.seen(TOOL_CALL_STARTED), app.listener.seen(TOOL_CALL_ENDED)
    assert (started["name"], started["arguments"], started["producer"]) == ("add", {"a": 17, "b": 25}, "model")
    assert (ended["ok"], ended["result"]) == (True, "42")

def test_several_calls_of_one_reply_run_in_their_order(chat):
    add = Add()
    app = chat([Reply(tool_calls=[ToolCall("add", {"a": 1, "b": 1}), ToolCall("add", {"a": 2, "b": 2})]),
                Reply(content="2 et 4.")])
    app._App__toolManager.register(add)
    app._App__answer("1+1 et 2+2 ?")
    assert tool_results(app) == ["2", "4"]

def test_an_unknown_or_broken_tool_is_an_error_the_model_reads(chat):
    app = chat([Reply(tool_calls=[ToolCall("teleport", {})]), Reply(tool_calls=[ToolCall("crash", {})]),
                Reply(content="Je n'y arrive pas.")])
    app._App__toolManager.register(Crashing())
    app._App__answer("Fais-le")
    unknown, crashed = tool_results(app)
    assert failed(unknown) and "'teleport' n'existe pas" in unknown and "tree" in unknown
    assert failed(crashed) and "disque plein" in crashed
    assert [data["ok"] for data in app.listener.seen(TOOL_CALL_ENDED)] == [False, False]
    assert app.listener.seen(CHAT_TURN_ENDED)[-1]["reason"] == "done"

def test_a_model_that_never_stops_calling_is_stopped_after_its_rounds(chat):
    app = chat([Reply(tool_calls=[ToolCall("add", {"a": n, "b": n})]) for n in range(3)], **{"chat.tools.maxdepth": 3})
    app._App__toolManager.register(Add())
    app._App__answer("Compte")
    assert app.listener.seen(CHAT_TURN_ENDED)[-1]["reason"] == "rounds"
