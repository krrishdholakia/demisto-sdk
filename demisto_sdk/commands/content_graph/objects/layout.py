from typing import List, Optional, Set, Union

from pydantic import Field

from demisto_sdk.commands.common.constants import MarketplaceVersions
from demisto_sdk.commands.content_graph.common import ContentType
from demisto_sdk.commands.content_graph.objects.content_item import ContentItem


class Layout(ContentItem, content_type=ContentType.LAYOUT):  # type: ignore[call-arg]
    kind: Optional[str]
    tabs: Optional[List[str]]
    definition_id: Optional[str] = Field(alias="definitionId")
    group: str
    edit: bool
    indicators_details: bool
    indicators_quick_view: bool
    quick_view: bool
    close: bool
    details: bool
    details_v2: bool
    mobile: bool

    def metadata_fields(self) -> Set[str]:
        return {"name", "description"}

    def prepare_for_upload(
        self, marketplace: MarketplaceVersions = MarketplaceVersions.XSOAR, **kwargs
    ) -> dict:
        # marketplace is the marketplace for which the content is prepared.
        data = super().prepare_for_upload(marketplace, **kwargs)
        data = self._fix_from_and_to_server_version(data)

        if marketplace == MarketplaceVersions.MarketplaceV2:
            data = fix_widget_incident_to_alert(data)

        return data

    def _fix_from_and_to_server_version(self, data: dict) -> dict:
        # On Layouts, we manually add the `fromServerVersion`, `toServerVersion` fields, see CIAC-5195.
        data["fromServerVersion"] = self.fromversion
        data["toServerVersion"] = self.toversion
        return data


def fix_widget_incident_to_alert(data: dict) -> dict:
    """
    Changes internal {name: 'Related Incidents', ... }, into {name: 'Related Alerts', ... }, see the condition below.
    """
    if not isinstance(data, dict):
        raise TypeError(f"expected dictionary, got {type(data)}")

    def fix_recursively(datum: Union[list, dict]) -> Union[list, dict]:
        if isinstance(datum, dict):
            if (
                datum.get("id") == "relatedIncidents"
                and datum.get("name") == "Related Incidents"
                and datum.get("name_x2") is None
            ):  # the kind of dictionary we want to fix
                datum["name"] = "Related Alerts"
                return datum
            else:  # not the atomic dictionary that we fix, use recursion instead.
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
