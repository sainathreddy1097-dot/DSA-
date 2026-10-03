"""Successive-shortest-path min-cost max-flow reviewer assignment.

Problem
    Assign contracts awaiting review to reviewers so that the number of valid
    assignments is maximal, and among maximal assignments the total
    workload/expertise cost is minimal.

Objectives (in priority order)
    1. Maximize the number of valid assignments (maximum flow).
    2. Minimize total cost (each augmentation follows a shortest path).

Model
    source      -> contract : capacity 1, cost 0
    contract    -> reviewer : capacity 1, cost = workload * 10 + expertise_gap * 100
    reviewer    -> sink     : capacity max(0, capacity - workload), cost 0

    An edge from a contract to a reviewer only exists when the reviewer's
    expertise intersects the contract's required expertise, so an incompatible
    pair can never be selected.

Cost
    cost(contract, reviewer) = existing_workload * 10 + expertise_gap * 100
    Load balancing is therefore preferred over an expertise gap, while an
    expertise gap is strongly penalised.

Data structures
    - Adjacency list of ``Edge`` records: ``to``, ``reverse`` (index of the
      paired residual edge), ``capacity``, ``cost`` and ``original_capacity``.
      Each forward edge is paired with a zero-capacity reverse edge of negated
      cost, which is what lets the algorithm undo an earlier decision.
    - ``tracked``: ``(contract_id, reviewer_id) -> Edge`` map used to read the
      final assignment back out of the residual graph.
    - ``distance`` / ``previous`` / ``in_queue``: SPFA shortest-path state.

Complexity
    With V = 2 + T + R nodes and E edges, each augmentation costs O(V * E) for
    SPFA and the flow value is at most T, giving O(T * V * E) time and
    O(V + E) space.

Determinism
    Tasks and reviewers are sorted by id before graph construction, SPFA only
    relaxes on a strict improvement, and the read-back iterates the sorted
    lists, so identical inputs always produce identical output.
"""

from dataclasses import dataclass
from collections import deque


@dataclass
class Edge:
    to: int
    reverse: int
    capacity: int
    cost: int
    original_capacity: int


def _add_edge(graph: list[list[Edge]], source: int, target: int, capacity: int, cost: int) -> Edge:
    forward = Edge(target, len(graph[target]), capacity, cost, capacity)
    backward = Edge(source, len(graph[source]), 0, -cost, 0)
    graph[source].append(forward)
    graph[target].append(backward)
    return forward


def _explain(task: dict, reviewer: dict, cost: int) -> str:
    """Build a human-readable justification from the real cost inputs."""
    required = set(task.get("requiredExpertise", []))
    expertise = set(reviewer.get("expertise", []))
    matched = sorted(required & expertise)
    gap = sorted(required - expertise)
    workload = int(reviewer.get("workload", 0))
    workload_cost = workload * 10
    gap_cost = len(gap) * 100
    return (
        f"Matched expertise {', '.join(matched) if matched else 'none'}; "
        f"workload {workload} of {int(reviewer.get('capacity', 0))}; "
        f"cost {cost} = {workload_cost} (workload {workload} x 10) + "
        f"{gap_cost} (expertise gap {len(gap)} x 100)"
    )


def _reason_for(task: dict, eligible: dict[str, int]) -> str:
    """Explain why a contract could not be assigned."""
    if eligible.get(task["id"], 0) == 0:
        required = sorted(task.get("requiredExpertise", []))
        return f"No active reviewer covers the required expertise: {', '.join(required) if required else 'none'}"
    return f"All {eligible[task['id']]} eligible reviewer(s) are already at capacity"

def propose_assignments(tasks: list[dict], reviewers: list[dict]) -> dict:
    """Run min-cost max-flow and return assignments plus full explanations.

    ``tasks`` items need ``id`` and optional ``requiredExpertise``.
    ``reviewers`` items need ``id``, optional ``expertise``, ``capacity`` and
    ``workload``. The result is deterministic for a given input.
    """
    ordered_tasks = sorted(tasks, key=lambda item: item["id"])
    ordered_reviewers = sorted(reviewers, key=lambda item: item["id"])
    source = 0
    task_offset = 1
    reviewer_offset = task_offset + len(ordered_tasks)
    sink = reviewer_offset + len(ordered_reviewers)
    graph: list[list[Edge]] = [[] for _ in range(sink + 1)]
    tracked: dict[tuple[str, str], Edge] = {}
    eligible: dict[str, int] = {task["id"]: 0 for task in ordered_tasks}

    for task_index, task in enumerate(ordered_tasks):
        task_node = task_offset + task_index
        _add_edge(graph, source, task_node, 1, 0)
        required = set(task.get("requiredExpertise", []))
        for reviewer_index, reviewer in enumerate(ordered_reviewers):
            expertise = set(reviewer.get("expertise", []))
            if required and not (required & expertise):
                continue
            expertise_gap = len(required - expertise)
            cost = int(reviewer.get("workload", 0)) * 10 + expertise_gap * 100
            edge = _add_edge(graph, task_node, reviewer_offset + reviewer_index, 1, cost)
            tracked[(task["id"], reviewer["id"])] = edge
            eligible[task["id"]] += 1
    for reviewer_index, reviewer in enumerate(ordered_reviewers):
        available = max(0, int(reviewer.get("capacity", 0)) - int(reviewer.get("workload", 0)))
        _add_edge(graph, reviewer_offset + reviewer_index, sink, available, 0)

    flow = 0
    total_cost = 0
    node_count = len(graph)
    infinite = 10**18
    while True:
        distance = [infinite] * node_count
        previous: list[tuple[int, int] | None] = [None] * node_count
        in_queue = [False] * node_count
        distance[source] = 0
        queue = deque([source])
        in_queue[source] = True
        while queue:
            node = queue.popleft()
            in_queue[node] = False
            for edge_index, edge in enumerate(graph[node]):
                if edge.capacity <= 0:
                    continue
                candidate = distance[node] + edge.cost
                if candidate < distance[edge.to]:
                    distance[edge.to] = candidate
                    previous[edge.to] = (node, edge_index)
                    if not in_queue[edge.to]:
                        queue.append(edge.to)
                        in_queue[edge.to] = True
        if previous[sink] is None:
            break
        node = sink
        while node != source:
            prior, edge_index = previous[node]
            edge = graph[prior][edge_index]
            edge.capacity -= 1
            graph[node][edge.reverse].capacity += 1
            node = prior
        flow += 1
        total_cost += distance[sink]

    assignments: list[dict] = []
    assigned_ids: set[str] = set()
    for task in ordered_tasks:
        for reviewer in ordered_reviewers:
            edge = tracked.get((task["id"], reviewer["id"]))
            if edge is not None and edge.original_capacity == 1 and edge.capacity == 0:
                required = set(task.get("requiredExpertise", []))
                expertise = set(reviewer.get("expertise", []))
                assignments.append({
                    "contractId": task["id"],
                    "reviewerId": reviewer["id"],
                    "cost": edge.cost,
                    "confidence": "Strong fit" if required <= expertise else "Good fit",
                    "explanation": _explain(task, reviewer, edge.cost),
                })
                assigned_ids.add(task["id"])

    proposed_counts: dict[str, int] = {reviewer["id"]: 0 for reviewer in ordered_reviewers}
    for item in assignments:
        proposed_counts[item["reviewerId"]] += 1
    reviewer_loads = [{
        "reviewerId": reviewer["id"],
        "capacity": int(reviewer.get("capacity", 0)),
        "existingWorkload": int(reviewer.get("workload", 0)),
        "proposedCount": proposed_counts[reviewer["id"]],
        "projectedLoad": int(reviewer.get("workload", 0)) + proposed_counts[reviewer["id"]],
        "remainingCapacity": max(0, int(reviewer.get("capacity", 0))
                                 - int(reviewer.get("workload", 0))
                                 - proposed_counts[reviewer["id"]]),
    } for reviewer in ordered_reviewers]

    return {
        "assignments": assignments,
        "assignedCount": flow,
        "totalCost": total_cost,
        "unassignedContractIds": [task["id"] for task in ordered_tasks if task["id"] not in assigned_ids],
        "unassigned": [{"contractId": task["id"], "reason": _reason_for(task, eligible)}
                       for task in ordered_tasks if task["id"] not in assigned_ids],
        "reviewerLoads": reviewer_loads,
        "eligiblePairs": len(tracked),
    }
