"""Base Script for Cortex XSOAR - Unit Tests file

Pytest Unit Tests: all funcion names must start with "test_"

More details: https://xsoar.pan.dev/docs/integrations/unit-testing

MAKE SURE YOU REVIEW/REPLACE ALL THE COMMENTS MARKED AS "TODO"

"""

import json

from demisto_sdk.commands.common.tools import get_json


# TODO: REMOVE the following dummy unit test function
def test_basescript_dummy():
    """Tests helloworld-say-hello command function.

    Checks the output of the command function with the expected output.

    No mock is needed here because the say_hello_command does not call
    any external API.
    """
    from BaseScript import basescript_dummy_command

    args = {"dummy": "this is a dummy response"}
    response = basescript_dummy_command(args)

    mock_response = get_json("test_data/basescript-dummy.json")

    assert response.outputs == mock_response


# TODO: ADD HERE your unit tests
