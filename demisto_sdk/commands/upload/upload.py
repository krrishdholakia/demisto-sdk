import logging
from pathlib import Path
import shutil
import tempfile
from typing import Optional
import os

import typer

app = typer.Typer()
logger = logging.getLogger('demisto-sdk')


@app.command(no_args_is_help=True)
def upload(
    ctx: typer.Context,
    input: Optional[Path] = typer.Argument(
        ...,
        exists=True,
        dir_okay=True,
        resolve_path=True,
        show_default=False,
        help=(
            'The path of file or a directory to upload. The following are supported:\n - Pack\n - A content entity'
            ' directory that is inside a pack. For example: an Integrations directory or a Layouts directory.\n - '
            'Valid file that can be imported to Cortex XSOAR manually. For example a playbook: helloWorld.yml.'
        )
    ),
    input_config_file: Optional[Path] = typer.Option(
        None,
        '--input-config-file',
        exists=True,
        dir_okay=False,
        resolve_path=True,
        show_default=False,
        help='The path to the config file to download all the custom packs from.'
    ),
    zip: bool = typer.Option(
        False,
        '-z', '--zip',
        show_default=True,
        help=(
            'Whether to zip the content before uploading it. This flag is relevant only when uploading a pack.'
            ' Must be passed when uploading to an XSIAM server, e.g. -x was passed.'
        )
    ),
    xsiam: bool = typer.Option(
        False,
        '-x', '--xsiam',
        show_default=True,
        help='Upload a pack to an XSIAM server.'
    ),
    zip_output: Optional[Path] = typer.Option(
        None,
        '-zo', '--zip-output',
        exists=True,
        dir_okay=True,
        resolve_path=True,
        show_default=False,
        help=(
            'The path to a directory in which to save the zip file. If not given, the zip file will be deleted.'
            ' This flag is relevant only when uploading a pack and the "--zip"/"-z" flag is used.'
        ),
    ),
    insecure: bool = typer.Option(
        False,
        '--insecure',
        show_default=True,
        help='Skip certificate validation.'
    ),
    skip_validation: bool = typer.Option(
        False,
        '--skip-validation',
        show_default=True,
        help=(
            'Only relevant when uploading a pack with the "--zip"/"-z" flag. If passed, the pack contents will not be'
            ' validated.'
        )
    ),
    reattach: bool = typer.Option(
        False,
        '--reattach',
        show_default=True,
        help=(
            'Reattach the detached files in the XSOAR instance for the CI/CD Flow. If you set the'
            ' "--input-config-file" flag, any detached item in your XSOAR instance that isn\'t currently'
            ' in the repo\'s SystemPacks folder will be re-attached.'
        )
    ),
    keep_zip: Optional[Path] = typer.Option(
        None,
        '--keep-zip',
        exists=True,
        dir_okay=True,
        resolve_path=True,
        show_default=False,
        help=(
            'The path to a directory in which to save the zip file. If not given, the zip file will be deleted.'
            ' This flag is relevant only when uploading a pack and the "--zip"/"-z" flag is used.\n Note: deprecated -'
            ' please use "--zip-output" instead.'
        ),
        rich_help_panel='Deprecated Options'
    ),
    verbose: bool = typer.Option(
        False,
        '-v', '--verbose',
        show_default=True,
        help=(
            'Verbose output.\nNote: deprecated - please use the top level "demisto-sdk" command line '
            'verbosity options instead.'
        ),
        rich_help_panel='Deprecated Options'
    ),
):
    from demisto_sdk.commands.upload.uploader import ConfigFileParser, Uploader
    from demisto_sdk.commands.common.constants import (ENV_DEMISTO_SDK_MARKETPLACE,
                                                       MarketplaceVersions)
    from demisto_sdk.commands.zip_packs.packs_zipper import (EX_FAIL,
                                                             PacksZipper)
    from demisto_sdk.utils import check_configuration_file
    pack_names = None
    output_zip_path = None
    detached_files = False
    if input:
        input_path = input.as_posix()
    if zip or input_config_file:
        if zip:
            pack_path = input
        else:
            config_file_to_parse = ConfigFileParser(config_file_path=input_config_file.as_posix())
            pack_path = config_file_to_parse.parse_file()
            detached_files = True
        if xsiam:
            marketplace = MarketplaceVersions.MarketplaceV2.value
        else:
            marketplace = MarketplaceVersions.XSOAR.value
        os.environ[ENV_DEMISTO_SDK_MARKETPLACE] = marketplace.lower()

        if zip_output or keep_zip:
            if zip_output:
                output_zip_path = zip_output.as_posix()
            elif keep_zip:
                output_zip_path = keep_zip.as_posix()
        output_zip_path = output_zip_path or tempfile.mkdtemp()
        packs_unifier = PacksZipper(pack_paths=pack_path, output=output_zip_path,
                                    content_version='0.0.0', zip_all=True, quiet_mode=True, marketplace=marketplace)
        packs_zip_path, pack_names = packs_unifier.zip_packs()
        if packs_zip_path is None and not detached_files:
            return EX_FAIL

        input_path = packs_zip_path

    check_configuration_file('upload', ctx.args)
    uploader = Uploader(
        input=input_path, insecure=insecure, skip_validation=skip_validation,
        verbose=verbose, pack_names=pack_names,
        detached_files=detached_files, reattach=reattach
    )
    upload_result = uploader.upload()
    if (zip or input_config_file) and not (keep_zip or zip_output):
        if output_zip_path:
            shutil.rmtree(output_zip_path, ignore_errors=True)
    return upload_result


if __name__ == "__main__":
    app()
