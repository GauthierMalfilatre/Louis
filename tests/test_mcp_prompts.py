##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Tests of the prompts of the MCP servers: each one a command /<server>:<prompt>, its arguments taken from what the
## user typed, what the server wrote sent to the model as the message of the user; the commands come and go with the
## servers and their prompts
##
import pytest
from conftest import CALC, Person, fake
from command.impl.command_mcp_prompt import McpPromptCommand
from events.event_list import APP_STARTED, COMMAND_ERROR, COMMAND_UNKNOWN, MCP_CHANGED, MCP_PROMPT
from interface.cli import mcp_prompt_usage
from model.reply import Reply
from tool.tool_call import ToolCall

PROMPTS = fake("fake", "--prompts")

def commands(app) -> set[str]:
    return {command.name for command in app._App__commands.commands}

def run(app, typed: str) -> bool:
    return app._App__commands.fetch(typed, app)

class Server:
    """ What a command needs of its server to read what the user typed """
    name = "srv"

def command(*arguments: dict) -> McpPromptCommand:
    return McpPromptCommand(Server(), {"name": "p", "arguments": list(arguments)})

# Commands

def test_the_prompts_of_the_servers_are_commands_from_the_start(louis):
    user = Person()
    app = louis([PROMPTS, CALC], [], user)
    assert {"fake:greet", "fake:pair", "fake:empty", "fake:broken", "calc:explain"} <= commands(app)
    [started] = user.seen(APP_STARTED)
    explain = next(described for described in started["commands"] if described["name"] == "calc:explain")
    assert explain["usage"] == "<expression>" and explain["description"].startswith("[MCP calc] Calcule")
    described = app.mcp.server("fake").describe()["prompts"]
    assert [mcp_prompt_usage(prompt) for prompt in described] == ["/fake:greet <name>", "/fake:pair <first> [second]",
                                                                  "/fake:empty", "/fake:broken"]

def test_a_prompt_is_answered_by_the_model_as_a_message_of_the_user(louis):
    user = Person()
    app = louis([CALC], [Reply(content="", tool_calls=[ToolCall("calc__calculate", {"expression": "(3+4)*sqrt(16)"})]),
                         Reply(content="(3+4) = 7, puis 7 × 4 = 28.")], user)
    assert run(app, "/calc:explain (3+4)*sqrt(16)")
    [prompt] = user.seen(MCP_PROMPT)
    assert (prompt["server"], prompt["prompt"], prompt["command"]) == ("calc", "explain", "calc:explain")
    assert app.sent[0][-1]["role"] == "user" and "Calcule (3+4)*sqrt(16) avec l'outil calculate" in app.sent[0][-1]["content"]
    assert [message["content"] for message in app.session.history if message["role"] == "tool"] == ["(3+4)*sqrt(16) = 28"]

def test_what_the_server_wrote_as_the_assistant_is_marked_so(louis):
    app = louis([PROMPTS], [Reply(content="Vu.")], Person())
    run(app, "/fake:pair un deux")
    sent: str = app.sent[0][-1]["content"]
    assert sent == "Premier : un\n\n(réponse de l'assistant) Compris.\n\nSecond : deux"

@pytest.mark.parametrize("typed, why", [
    ("/fake:greet", "usage"),
    ("/fake:broken", "failed"),
    ("/fake:empty", "empty"),
    ("/fake:pair a b c", "usage"),
    ('/fake:pair "a', "usage"),
])
def test_a_prompt_that_can_not_be_run_is_told_and_nothing_is_sent(louis, typed, why):
    user = Person()
    app = louis([PROMPTS], [], user)
    assert run(app, typed)
    assert [error["reason"] for error in user.seen(COMMAND_ERROR)] == [why]
    assert app.sent == [] and user.seen(MCP_PROMPT) == []

def test_the_commands_of_a_server_go_and_come_back_with_it(louis):
    user = Person()
    app = louis([PROMPTS], [], user)
    run(app, "/mcp stop fake")
    assert not any(name.startswith("fake:") for name in commands(app))
    assert run(app, "/fake:greet Ana") and user.seen(COMMAND_UNKNOWN)[-1]["name"] == "fake:greet"
    run(app, "/mcp restart fake")
    assert "fake:greet" in commands(app)
    assert "fake:greet" in [described["name"] for described in user.seen(MCP_CHANGED)[-1]["commands"]]

def test_a_prompt_the_server_added_is_a_command_at_the_next_message(louis):
    user = Person()
    app = louis([PROMPTS], [Reply(content="", tool_calls=[ToolCall("fake__more_prompts", {})]), Reply(content="Fait."),
                            Reply(content="Encore.")], user)
    app.answer("Ajoute un prompt")
    assert "fake:added" not in commands(app)
    app.answer("Et maintenant ?")
    assert "fake:added" in commands(app)
    assert [(changed["server"], changed["change"]) for changed in user.seen(MCP_CHANGED)] == [("fake", "prompts")]

def test_a_path_typed_first_is_still_a_message(louis):
    app = louis([PROMPTS], [], Person())
    assert not run(app, "/src/main.py:12 que fait cette ligne ?")

# What the user typed

def test_a_prompt_of_one_argument_takes_the_whole_text():
    assert command({"name": "q", "required": True}).values(' le "texte" entier ') == {"q": 'le "texte" entier'}

def test_a_prompt_of_several_arguments_takes_words_in_their_order_or_by_their_name():
    two = command({"name": "a", "required": True}, {"name": "b"})
    assert two.values("un deux") == {"a": "un", "b": "deux"}
    assert two.values("b=deux un") == {"a": "un", "b": "deux"}
    assert two.values('"un mot" b="deux mots"') == {"a": "un mot", "b": "deux mots"}
    assert two.values("seul") == {"a": "seul"}

@pytest.mark.parametrize("arguments, typed, why", [
    ([{"name": "a", "required": True}, {"name": "b"}], "", "Il manque a"),
    ([{"name": "a", "required": True}, {"name": "b"}], "x y z", "Trop d'arguments : z"),
    ([{"name": "a"}, {"name": "b"}], "'x", "guillemet"),
    ([], "x", "ne prend pas d'argument"),
])
def test_what_is_wrong_in_what_the_user_typed_is_told(arguments, typed, why):
    with pytest.raises(ValueError, match=why):
        command(*arguments).values(typed)
