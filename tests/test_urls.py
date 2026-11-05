import pytest

from youtubetomp3.urls import UrlError, normalize_channel_videos_url


def test_handle_url_points_at_the_videos_tab():
    assert (
        normalize_channel_videos_url("https://www.youtube.com/@Some.Channel/featured?view=0")
        == "https://www.youtube.com/@Some.Channel/videos"
    )


def test_channel_id_and_custom_url_are_accepted():
    assert (
        normalize_channel_videos_url("youtube.com/channel/UC123")
        == "https://www.youtube.com/channel/UC123/videos"
    )
    assert (
        normalize_channel_videos_url("https://m.youtube.com/c/Name")
        == "https://www.youtube.com/c/Name/videos"
    )
    assert (
        normalize_channel_videos_url("https://www.youtube.com/user/Name/about")
        == "https://www.youtube.com/user/Name/videos"
    )


@pytest.mark.parametrize(
    "text",
    [
        "",
        "not a url",
        "@SomeChannel",
        "https://www.youtube.com/watch?v=abc",
        "https://www.youtube.com/playlist?list=PLxxxx",
        "https://www.youtube.com/shorts/abc",
        "https://youtu.be/abc",
    ],
)
def test_non_channel_text_is_rejected(text):
    with pytest.raises(UrlError):
        normalize_channel_videos_url(text)
