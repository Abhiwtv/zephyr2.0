import os
import json
import threading
import tempfile
from typing import Any, Union, List, Optional

_output_lock = threading.Lock()

def save_output_json(
    report_data: Union[dict, List[dict]],
    filepath: str = "output.json",
    append_mode: bool = False
) -> str:
    """
    Saves generated diagnostic output(s) to a JSON file in the exact same format
    as generated as OUTPUT by the multi-agent system.

    Args:
        report_data: A single report dictionary or a list of report dictionaries.
        filepath: Destination file path (default: 'output.json').
        append_mode: If True and filepath exists, merges/appends reports into a JSON array.
                     If False (default), writes report_data directly in its exact native format.

    Returns:
        The path to the saved JSON file.
    """
    with _output_lock:
        abs_path = os.path.abspath(filepath)
        dir_name = os.path.dirname(abs_path)
        if dir_name and not os.path.exists(dir_name):
            try:
                os.makedirs(dir_name, exist_ok=True)
            except Exception:
                pass

        final_data = report_data

        if append_mode and os.path.exists(abs_path):
            try:
                with open(abs_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)

                if isinstance(existing, list):
                    report_list = list(existing)
                elif isinstance(existing, dict):
                    report_list = [existing]
                else:
                    report_list = []

                items_to_add = report_data if isinstance(report_data, list) else [report_data]
                existing_ids = {
                    r.get("incident_id"): idx
                    for idx, r in enumerate(report_list)
                    if isinstance(r, dict) and "incident_id" in r
                }

                for item in items_to_add:
                    if isinstance(item, dict) and item.get("incident_id") in existing_ids:
                        report_list[existing_ids[item["incident_id"]]] = item
                    else:
                        report_list.append(item)

                final_data = report_list
            except Exception as e:
                print(f"[OUTPUT WARNING] Failed to read existing {abs_path} for append: {e}. Overwriting.")
                final_data = report_data

        # Attempt atomic file write with graceful tempfile fallback for restricted environments
        try:
            temp_file = f"{abs_path}.tmp"
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(final_data, f, indent=2, ensure_ascii=False)

            if os.path.exists(abs_path):
                os.replace(temp_file, abs_path)
            else:
                os.rename(temp_file, abs_path)

            return abs_path
        except (PermissionError, OSError):
            fallback_dir = tempfile.gettempdir()
            fallback_file = os.path.join(fallback_dir, os.path.basename(filepath))
            with open(fallback_file, "w", encoding="utf-8") as f:
                json.dump(final_data, f, indent=2, ensure_ascii=False)
            return fallback_file


def load_output_json(filepath: str = "output.json") -> Optional[Union[dict, list]]:
    """Loads and returns the content of the output JSON file."""
    with _output_lock:
        target = filepath
        if not os.path.exists(target):
            fallback = os.path.join(tempfile.gettempdir(), os.path.basename(filepath))
            if os.path.exists(fallback):
                target = fallback
            else:
                return None
        with open(target, "r", encoding="utf-8") as f:
            return json.load(f)
