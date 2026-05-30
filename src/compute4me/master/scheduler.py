"""Smart-pull scheduler: assign best-fit eligible Tasks to free Workers.

Holds a priority queue of pending Tasks; ``next_task_for(worker)`` applies the
feasibility filter, then cached-input locality preference, then fast-Worker-gets-biggest.
Runs one Job at a time per Room, FIFO. See ADR-0008.

Populated in T16.
"""

from __future__ import annotations
