import logging

from demisto_sdk.commands.common.constants import MarketplaceVersions
from demisto_sdk.commands.prepare_content.preparers.incident_to_alert import (
    prepare_script_access_fields,
    create_wrapper_script,
)

logger = logging.getLogger("demisto-sdk")


class MarketplaceIncidentToAlertScriptsPreparer:
    @staticmethod
    def prepare(data: dict,
                current_marketplace: MarketplaceVersions,
                incident_to_alert: bool) -> tuple:
        """
        Two cases in which script preparation is needed:
        - incident_to_alert is false:
            Iterate on the fields name description comment and id,
            and removes if there is a wrapper for the word incident such as <-incident->.
        - incident_to_alert is true:
            Apart from the above preparation,
            two scripts will be created,
            1. The existing script so that in the name, description, comment and id fields
               the word `incident` will be replaced by `alert` when the word `incident` is not wrapped like this <-incident->.
               
            2. A wrapper script that will call the script with the new name,
               all the fields of the script will remain as they are and the word incident will not be replaced.

        Args:
            data: content item data
            current_marketplace: the destination marketplace.
            incident_to_alert: A boolean flag that determines whether a new script and a wrapper script should be created.

        Returns:
            Tuple[dict]: A tuple of two scripts, the wrapper script and the modified original script.
        """
        scripts_preparation = []

        # Creating a wrapper script
        if incident_to_alert:
            scripts_preparation.append(create_wrapper_script(data))

        # Handling the incident word in the script
        scripts_preparation.append(prepare_script_access_fields(data, incident_to_alert))
        logging.debug(f"Script preparation {data['name']} completed")

        return tuple(scripts_preparation)
