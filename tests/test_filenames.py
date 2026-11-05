from youtubetomp3.filenames import mp3_name, sanitize_filename


def test_illegal_characters_become_spaces_and_edges_are_trimmed():
    assert sanitize_filename('  hello?: world. ', "fallback") == "hello world"


def test_empty_title_uses_the_fallback():
    assert sanitize_filename(" ... ", "abc123") == "abc123"


def test_windows_reserved_name_is_adjusted():
    assert sanitize_filename("CON", "abc") == "CON_"


def test_mp3_name_keeps_the_title():
    assert mp3_name("Interview", "abc") == "Interview.mp3"
