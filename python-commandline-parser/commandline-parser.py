"""
Commandline parser in a single file with no external dependencies.

Note: Needs python 3.9 due to dict merge operator (|)
"""

import sys


class Command:
    def __init__(self, description):
        self.description = description
        self.positionals = []
        self.upcoming_positionals_optional = False
        self.switches = {}
        self.subcommands = {}
        self.subcommands_optional = False

    def positional(self, name, description, parser):
        assert name != "command", "name 'command' is reserved for subcommands"

        self.positionals.append(
            {
                "name": name,
                "description": description,
                "parser": parser,
                "optional": self.upcoming_positionals_optional,
            }
        )
        return self

    def optional_positionals(self):
        self.upcoming_positionals_optional = True

    def optional_subcommands(self):
        self.subcommands_optional = True

    def switch(self, switches, name, description, parser, *, optional=False, **kwargs):
        assert name != "command", "name 'command' is reserved for subcommands"

        switch_info = {
            "name": name,
            "switches": switches,
            "description": description,
            "parser": parser,
            "optional": optional,
        }

        if "default" in kwargs:
            switch_info["default"] = kwargs["default"]

        for switch in switches:
            self.switches[switch] = switch_info
        return self

    def subcommand(self, name, cmd):
        self.subcommands[name] = cmd
        return self

    def parse(self, binary="script.py"):
        argv_iter = enumerate(sys.argv)
        _, binary = next(argv_iter, binary)

        if len(sys.argv) <= 1 or "--help" in sys.argv:
            self.print_usage(binary)
            sys.exit(-1)

        try:
            return self._parse(argv_iter)
        except CommandLineError as e:
            print()
            print(e.render_message(sys.argv))
            sys.exit(-1)

    def print_usage(self, binary, indent=2):
        print()
        self._print_usage(binary, indent_start=0, indent_incr=indent)

    def _parse(self, argv_iter):
        out = {}
        positional_index = 0
        for i, arg in argv_iter:
            if arg.startswith("-"):
                arg, eq, val = arg.partition("=")
                if eq == "":
                    val = None
                if arg in self.switches:
                    out = out | parse_arg(i, arg, val, self.switches[arg])
                else:
                    raise UnknownSwitch(i, arg)
            elif arg in self.subcommands:
                out = out | {
                    "command": arg,
                    arg: self.subcommands[arg].parse(argv_iter),
                }
            else:
                if positional_index >= len(self.positionals):
                    raise TooManyPositionals(i, arg)

                out = out | parse_arg(i, None, arg, self.positionals[positional_index])
                positional_index += 1

        for positional in self.positionals:
            if not positional["optional"] and positional["name"] not in out:
                raise MissingOption(positional["name"])

        for switch in self.switches.values():
            if not switch["optional"] and switch["name"] not in out:
                name = switch["name"]
                if "default" in switch:
                    out[name] = switch["default"]
                else:
                    switches = ", ".join(switch["switches"])
                    raise MissingOption(f"{name} ({switches})")

        if (
            len(self.subcommands) > 0
            and not self.subcommands_optional
            and "command" not in out
        ):
            subcommands = ", ".join(self.subcommands)
            raise MissingOption(f"command ({subcommands})")

        return out

    def _print_usage(self, name, indent_start=0, indent_incr=2):
        s = _bold(name)
        for arg in self.positionals:
            s1 = arg["name"]
            if arg["optional"]:
                s += " [" + s1 + "]"
            else:
                s += " " + s1

        switches = {s["name"]: s for s in self.switches.values()}.values()

        if self.switches:
            for arg in switches:
                s1 = "/".join(arg["switches"])
                if isinstance(arg["parser"], str) and arg["parser"] != "bool":
                    s1 += "=" + arg["parser"]
                elif isinstance(arg["parser"], list):
                    s1 += "=" + "/".join(arg["parser"])

                if arg["optional"]:
                    s += " [" + s1 + "]"
                else:
                    s += " " + s1

        if self.subcommands:
            if self.subcommands_optional:
                s += " [command]"
            else:
                s += " command"

        sp = " " * indent_start
        print(sp + s)

        if self.positionals:
            for arg in self.positionals:
                print_usage(arg, indent_start + indent_incr)

        if self.switches:
            for arg in {s["name"]: s for s in self.switches.values()}.values():
                print_usage(arg, indent_start + indent_incr)

        if self.subcommands:
            for name, cmd in self.subcommands.items():
                print()
                cmd._print_usage(
                    name,
                    indent_start=indent_start + indent_incr,
                    indent_incr=indent_incr,
                )
            print()


def parse_arg(i, arg, val, argdef):
    name = argdef["name"]
    parser = argdef["parser"]

    if parser != "bool" and val == None:
        raise ValueNotProvided(i)

    if parser == "str":
        parsed_val = val
    elif parser == "int":
        try:
            parsed_val = int(val)
        except ValueError:
            raise InvalidOption(i, "int", val)  # todo
    elif parser == "float":
        try:
            parsed_val = float(val)
        except ValueError:
            raise InvalidOption(i, "float", val)  # todo
    elif parser == "bool":
        if val == None or val.lower() in ["1", "true"]:
            parsed_val = True
        elif val.lower() in ["0", "false"]:
            parsed_val = False
        else:
            raise InvalidOption(i, "bool switch", val)  # todo
    elif isinstance(parser, list):
        vals = parser
        if val in vals:
            parsed_val = val
        else:
            raise InvalidOption(i, "/".join(vals), val)
    else:
        parsed_val = parser(i, arg, val)

    return {name: parsed_val}


def print_usage(arg, indent):
    if isinstance(arg["parser"], str):
        value = arg["parser"]
    elif isinstance(arg["parser"], list):
        value = "/".join(arg["parser"])
    else:
        value = None

    if "switches" in arg:
        name = ", ".join(sorted(arg["switches"], key=lambda x: len(x)))
    else:
        name = arg["name"]

    print(_pad(name, 8, indent) + arg["description"])

    if value:
        print(_pad("", 8, indent) + value)


# Errors


class CommandLineError(Exception):
    def __init__(self, index, message):
        self.index = index
        self.message = message

    def render_message(self, args):
        if self.index is not None:
            correction = _highlight_incorrect(args, self.index)
        else:
            correction = ""
        return f"{_red('Error: ')}{self.message} \n\n" + correction


class UnknownSwitch(CommandLineError):
    def __init__(self, index, switch):
        super().__init__(index, f"Unknown switch: {switch}")


class MissingOption(CommandLineError):
    def __init__(self, option):
        super().__init__(None, f"Missing option: {option}")


class TooManyPositionals(CommandLineError):
    def __init__(self, index, val):
        super().__init__(index, f"Too many arguments received: {val}")


class InvalidOption(CommandLineError):
    def __init__(self, index, expected, got):
        super().__init__(index, f"Expected {expected}, got {got}")


class ValueNotProvided(CommandLineError):
    def __init__(self, index):
        super().__init__(index, f"Value not provided for a non-boolean option")


# Utils


def _highlight_incorrect(argv, incorrect_index):
    binary = argv[0]
    sep = " "

    correct_part_1 = sep.join(argv[1:incorrect_index])
    wrong_part = argv[incorrect_index]
    correct_part_2 = sep.join(argv[incorrect_index + 1 :])

    return binary + sep + sep.join((correct_part_1, _red(wrong_part), correct_part_2))


def _red(s):
    bright_red = "\033[0;91m"
    reset_colour = "\033[0m"
    return bright_red + s + reset_colour


def _bold(s):
    bold = "\033[1m"
    reset_colour = "\033[0m"
    return bold + s + reset_colour


def _pad(s, x, indent=0):
    if len(s) < x:
        return " " * indent + s + " " * (x - len(s))
    else:
        return " " * indent + s + "\n" + " " * (indent + x)
