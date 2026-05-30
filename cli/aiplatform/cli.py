"""aiplatform CLI root — Click group with --version and --env flags.

Binary name is ``aiplatform`` (was ``aitana`` until 2026-04-28, renamed
to avoid clashes with unrelated tools that share the brand prefix on
contributors' machines).
"""

from __future__ import annotations

import click

from aiplatform import __version__
from aiplatform.commands.access import access
from aiplatform.commands.bucket import bucket
from aiplatform.commands.docs import docs
from aiplatform.commands.folder import folder
from aiplatform.commands.groups import groups
from aiplatform.commands.sessions import sessions
from aiplatform.commands.skill import skill


@click.group()
@click.version_option(__version__, "--version", "-V", prog_name="aiplatform")
@click.option(
    "--env",
    type=click.Choice(["dev", "test", "prod", "local"]),
    default="local",
    show_default=True,
    help="Target environment. Backend URL is resolved from AIPLATFORM_API_URL / AIPLATFORM_API_URL_<ENV>.",
)
@click.pass_context
def main(ctx: click.Context, env: str) -> None:
    """Aitana Labs CLI — bucket/folder/groups/access/skill admin for the v6 platform."""
    ctx.ensure_object(dict)
    ctx.obj["env"] = env


main.add_command(bucket)
main.add_command(docs)
main.add_command(folder)
main.add_command(groups)
main.add_command(access)
main.add_command(skill)
main.add_command(sessions)


if __name__ == "__main__":
    main()
