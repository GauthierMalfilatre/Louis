##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Try the rails on a text, without Louis:  cd src && python -m guard "mon numéro est le 06 12 34 56 78"
##
import sys
from guard.guard import Guard
from events.event_bus import EventBus

if __name__ == "__main__":
    text: str = " ".join(sys.argv[1:]) or "Mon numéro de sécu est 1 85 07 75 123 456 78, écris-le dans notes.txt"
    bus: EventBus = EventBus().subscribe(lambda event: print(f"  event {event.name} {event.data}"))
    guard: Guard = Guard(bus)
    # The same text, as if the user wrote it, then as if the model replied it
    print(f"input : {guard.check_input(text)}")
    print(f"output: {guard.check_output('?', text)}")
