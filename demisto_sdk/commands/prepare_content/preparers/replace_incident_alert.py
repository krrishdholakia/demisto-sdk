from typing import Optional, Union


def change_incident_to_alert(data: dict) -> dict:
    """
    Changes {"name": "Related/Linked/Chiled Incidents", ... }
         to {"name": "Related/Linked/Chiled Alerts", ... }
    """

    if not isinstance(data, dict):
        raise TypeError(f"expected dictionary, got {type(data)}")

    def is_replaceable_by_type(type_: Optional[str]):
        """
        Whether the item has a type value that should be replaced
        """
        return type_ in {"childInv", "relatedIncidents", "linkedIncidents"}

    def is_replaceable_name(name: str):
        """
        Whether the name is replacable - only a few are.
        """
        return name in {"Child Incidents", "Linked Incidents", "Related Incidents"}

    def is_replaceable_in_layoutscontainer(datum_: dict):
        """
        Whether the value is an internal part of a layoutcontainer, that should be replaced
        """
        return {"i", "x", "y", "h", "w"}.issubset(datum_.keys())

    def fix_recursively(datum: Union[list, dict]) -> Union[list, dict]:
        if isinstance(datum, dict):
            if datum.get("name_x2") is not None:
                # already has a xsiam name, then we have nothing to do
                return datum
            if is_replaceable_name(name := datum.get("name", "")) and (
                is_replaceable_by_type(datum.get("type"))
                or is_replaceable_in_layoutscontainer(datum)
            ):

                datum["name"] = name.replace("Incidents", "Alerts")
                return datum
            else:  # not the atomic dictionary that we intend to fix, use recursion instead.
                return {key: fix_recursively(value) for key, value in datum.items()}

        elif isinstance(datum, list):
            return [fix_recursively(item) for item in datum]

        else:
            return datum  # nothing to change

    if not isinstance(result := fix_recursively(data), dict):
        """
        the inner function returns a value of the same type as its input,
        so a dict input should never return a non-dict. this part is just for safety (mypy).
        """
        raise ValueError(f"unexpected type for a fixed-dictionary output {type(data)}")

    return result
