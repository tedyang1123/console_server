def encode_console_clear_str():
    return chr(27) + "[2J" + chr(27) + "[3J" + chr(27) + "[1;1H"


def encode_console_prompt():
    return "Select > "

