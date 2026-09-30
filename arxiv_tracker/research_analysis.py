# -*- coding: utf-8 -*-
"""Merge per-direction arXiv query results."""


def merge_group_items(group_results):
    """Merge per-group query results by arXiv ID while preserving group matches."""
    by_id = {}
    merged = []
    for group_name, results in group_results:
        for item in results or []:
            aid = item.get("id")
            if aid and aid in by_id:
                names = by_id[aid].setdefault("groups", [])
                if group_name not in names:
                    names.append(group_name)
                continue
            copy = dict(item)
            copy["groups"] = list(dict.fromkeys((copy.get("groups") or []) + [group_name]))
            merged.append(copy)
            if aid:
                by_id[aid] = copy
    return merged
