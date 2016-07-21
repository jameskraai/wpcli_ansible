#!/usr/bin/python
# -*- coding: utf-8 -*-
# (c) 2016, James Kraai <james@jameskraai.com>

# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.
#

# ---- Documentation Start ----------------------------------------------------#
DOCUMENTATION = '''
---
module: wpcli
author:
 - "James Kraai"
short_description: WordPress Command Line Interface
version_added: "2.1.0.0"
description:
    - WP-CLI is a set of command-line tools for managing WordPress installations.
    - You can update plugins, configure multi-site installs and much more, without using a web browser.
options:
    free_form:
        description:
            - Top level command to run, there is no parameter called 'free form'.
            See the examples!
        required: true
        default: null
    subcommand:
        description:
          - Subcommand such as 'check-update' or 'install'.
        required: true
        default: null
    options:
        description:
            - CLI flag with a value such as '--version=1'
        required: false
        default: null
    flags:
        description:
            - CLI flag with no value such as '--skip-email'
    working_dir:
      description:
        - Directory of the WordPress installation.
      required: true
      default: null
requirements:
  - WP-CLI installed in bin path (recommended /usr/local/bin).
notes:
    - All output is suppressed using the --quiet flag.
'''

# ---- Logic Start ------------------------------------------------------------#

import os
import re
from ansible.module_utils.basic import *

try:
    import json
except ImportError:
    try:
        import simplejson as json
    except ImportError:
        # Let module_utils/basic.py return a proper error in this case.
        pass


class Option:
    """
    Represents an Option attached to a SubCommand.
    """
    name = ""
    accepts_values = False

    def __init__(self, name, accepts_values):
        """
        :param Bool accepts_values:
        """
        self.name = name
        self.accepts_values = accepts_values


class SubCommand:

    options = dict()

    """
    Represents a Sub Command that may have available options
    assigned to it.
    """

    def __init__(self, name, alias = False):
        """
        Sets the name of this Sub Command and sets
        the options property as an empty array.

        :arg      name The name of this Sub Command
        :arg bool alias Optional if the true command is not YAML compatible.
        """
        self.name = name

        if alias:
            self.name = alias

        self.options = dict()

    def add_option(self, name, accepts_values=False):
        """
        Adds an option to this Sub Command
        :param str name: Name of the option
        :param bool accepts_values: Whether this option accepts a value or not
        :return: self
        """

        self.options[name] = Option(name, accepts_values)

        return self


class Command:
    """
    Represents a top level command which may have multiple Sub Commands
    assigned to it.
    """
    subCommands = dict()

    def __init__(self, name):
        """
        :param name: Name of this Command.
        """

        self.name = name
        self.subCommands = dict()

    def add_sub_command(self, name, alias = False):
        """
        Add a new SubCommand instance to the subCommands property
        and then return the new Sub Command.
        :param name: Name of the SubCommand
        : param bool alias: Optional Alias in the case the sub command is not YAML compliant.
        :return: SubCommand
        """

        sub_command = SubCommand(name, alias)

        self.subCommands[name] = sub_command

        return sub_command

# core : Command
# Add the core top level command, with this we can manage the WordPress code such as
# adding Users or making a configuration file.
core = Command("core")
core.add_sub_command("install")\
    .add_option("url", True)\
    .add_option("title", True)\
    .add_option("admin_user", True)\
    .add_option("admin_password", True)\
    .add_option("admin_email", True)\
    .add_option("skip-email")

core.add_sub_command("update")\
    .add_option("minor")\
    .add_option("version", True)

core.add_sub_command("download")

core.add_sub_command("config")\
    .add_option("dbname", True)\
    .add_option("dbuser", True)\
    .add_option("dbpass", True)

core.add_sub_command("update")
core.add_sub_command("update-db")

core.add_sub_command("checkUpdate", "check-update")

# theme : Command
# Add theme top level command, with these we can update all themes.
theme = Command("theme")
theme.add_sub_command("update")\
    .add_option("all")

# plugin : Command
# Manage all of the plugins such as performing updates.
plugin = Command("plugin")
plugin.add_sub_command("update").add_option("all")

# Dictionary of all of the Commands available.
commands = dict(core=core, theme=theme, plugin=plugin)


def parse_out(string):
    return re.sub("\s+", " ", string).strip()


def get_command(module, command, available_commands):
    """
    Get a Command from the availableCommands dictionary.
    :param AnsibleModule module:
    :param Command       command:
    :param Dict          available_commands:
    :rtype: Command
    """
    if command in available_commands:
        return available_commands.get(command)

    return module.fail_json(msg="Command not available")


def get_sub_command(module, command, sub_command):
    """
    Get a Sub Command from those available on a Command class.
    :param AnsibleModule module:
    :param Command       command:
    :param SubCommand    sub_command:
    :rtype: SubCommand
    """
    if sub_command in command.subCommands:
        return command.subCommands.get(sub_command)

    return module.fail_json(msg="SubCommand not available in Command")


def get_sub_command_option(module, sub_command, option):
    """
    Get an Option instance attached to a specific SubCommand.
    :param AnsibleModule module:
    :param SubCommand    sub_command:
    :param str           option:
    :rtype: Option
    """
    if option in sub_command.options:
        return sub_command.options.get(option)

    return module.fail_json(msg="Option not available in SubCommand")


def get_formatted_options(module, sub_command, options=dict):
    """
    Checks if any options are set on the module, if we we will format them.
    Also since the 'working_dir' option is required we will set that
    as an Option since the WP CLI recognizes that as a global flag.

    :param AnsibleModule module:
    :param SubCommand    sub_command:
    :param dict          options:
    :rtype: array.array
    """

    formatted_options = []

    # Check to see if the options Dictionary is not empty.
    if options:
        # Iterate over the options Dictionary with as option => value.
        for option, value in options.iteritems():

            # First we must get an instance of the Option class with will
            # validate that this is a valid Option.
            option_instance = get_sub_command_option(module, sub_command, option)

            # Now let's check to see if the Option class reports that
            # this Option accepts values.
            if option_instance.accepts_values:
                # If this option does accept values then format the option in
                # the following format: --option=value. And then append to
                # the formatted_options array.
                formatted_options.append("--%s" % (option_instance.name + "=" + value))
                continue

            # Since the Option does not accept arguments then we must format the
            # Option in the following format: --option, and then append to
            # the formatted_options array.
            formatted_options.append("--%s" % option_instance.name)
    return formatted_options


def wp_better_command(module, command, subcommand, options):
    """
    Runs a WP Command

    :param AnsibleModule module:
    :param Command       command:
    :param SubCommand    subcommand:
    :param array.array         options:
    :return: mixed
    """
    wp_path = module.get_bin_path("wp", True, ["/usr/local/bin"])

    # Format the various parameters into an actual command string.
    cmd = "%s %s %s %s" % (wp_path, command.name, subcommand.name, " ".join(options))
    return module.run_command(cmd)


def main():
    module = AnsibleModule(
        argument_spec=dict(
            command=dict(type="str", required=True),
            subcommand=dict(type="str", required=True),
            arguments=dict(type="dict", required=False),
            working_dir=dict(required=True, type="str")
        ),
        supports_check_mode=True
    )

    # Get the WP command
    # Since this is a required argument as can pass the module 'command' parameter directly into our
    # 'get_command' function. What this function will do is ensure that this is a valid command.
    # If it is a valid command it will return a new Command class.
    parsed_command = get_command(module, module.params['command'], commands)

    # Get the Sub Command
    # This argument is required as well therefore we can pass the module 'subcommand' paremter directly into our
    # 'get_sub_command' function. This function accepts the AnsibleModule, a Command instance, and a string
    # of the Sub Command we would like to work with. Should the 'subcommand' be valid a new
    # Sub Command class instance will be returned.
    parsed_sub_command = get_sub_command(module, parsed_command, module.params['subcommand'])

    # Get the Options
    parsed_options = get_formatted_options(module, parsed_sub_command, module.params['arguments'])

    # The 'working_dir' argument is a global option that is required, therefore we
    # will append to the parsed options array.
    parsed_options.append("--path=%s" % module.params.get("working_dir"))

    rc, out, err = wp_better_command(module, parsed_command, parsed_sub_command, parsed_options)

    changed = False

    if rc != 0:
        output = parse_out(err)
        module.fail_json(msg=output, stdout=err, changed=changed)
        sys.exit(1)

    output = parse_out(out + err)

    if re.search("Success", output):
        changed = True

    if re.search("update_type", output):
        changed = True

    if re.search("0/0", output):
        changed = False

    if re.search("WordPress is at the latest version", output):
        changed = False

    module.exit_json(msg=output, stdout=out+err, changed=changed)


# ---- Import Ansible Utilities (Ansible Framework) ---------------------------#
if __name__ == '__main__':
    main()